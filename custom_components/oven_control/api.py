"""Client for the local HTTP API of Ofen Innovativ / Firecontrols stove controllers.

The controller exposes two endpoint families:

* ``/direct/<cmd>``: pass-through to the stove MCU. Request and response bodies are
  JSON objects ``{"raw": "<hex frame>"}``.
* ``/module/<name>``: the Wi-Fi module itself, plain JSON.

Frame layout: ``aacc3355 | len | cmd | payload | checksum``. ``len`` counts cmd and
payload bytes; lengths of 255 and more are encoded as ``ff`` followed by ``len - 255``.
The checksum is the 16-bit sum of cmd and payload bytes, little-endian. Requests send
``ffff`` instead of a checksum, like the vendor app does.

The controller handles one client at a time and resets connections when it is busy,
so all requests go through one lock, with a gap between them and retries.

This module does not depend on Home Assistant.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

FRAME_PREFIX = bytes.fromhex("aacc3355")
REQUEST_TRAILER = bytes.fromhex("ffff")

CMD_STATUS = 0x00
CMD_ALARM_LOG = 0x04
CMD_BURN_SETTINGS = 0x12
CMD_SET_BURN_SETTINGS = 0x13
CMD_WATER_SETTINGS = 0x20
CMD_SET_WATER_SETTINGS = 0x21
CMD_CLOCK = 0x22
CMD_SET_CLOCK = 0x23
CMD_MCU_INFO = 0x24
CMD_BURN_PARAMS = 0x30
CMD_SET_BURN_PARAMS = 0x31
CMD_ALARM_MASK = 0x32
CMD_SET_ALARM_MASK = 0x33

# Status byte values of 255 mean "no sensor".
NO_SENSOR = 255
WATER_TEMP_OFFSET = 50

# Alarm bits, shared by the live status byte and the alarm mask (cmd 0x32/0x33).
ALARM_HEATING_ERROR = 0x02
ALARM_FLAME_SENSOR_ERROR = 0x04
ALARM_BOILER_OVERHEAT = 0x08
ALARM_BUFFER_TOP_OVERHEAT = 0x20
ALARM_MASK_BITS = (
    ALARM_HEATING_ERROR
    | ALARM_FLAME_SENSOR_ERROR
    | ALARM_BOILER_OVERHEAT
    | ALARM_BUFFER_TOP_OVERHEAT
)

# Alarm log types as named by the vendor app. Types 16 and 17 occur on real devices
# but are unknown.
ALARM_LOG_TYPES = {
    0: "backup_battery",
    1: "heating_error",
    2: "flame_sensor_error",
    3: "boiler_overheat",
    4: "power_failure",
    5: "buffer_overheat",
    6: "board_overheat",
    52: "buffer_top_overheat",
}

ALARM_LOG_RECORDS = 70
ALARM_LOG_RECORD_SIZE = 6


class OvenError(Exception):
    """Base error of the oven client."""


class OvenConnectionError(OvenError):
    """The controller could not be reached or did not answer."""


class OvenProtocolError(OvenError):
    """The controller answered with something that is not a valid frame."""


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded ``/direct`` frame."""

    command: int
    payload: bytes

    def u8(self, index: int) -> int:
        """Return the payload byte at ``index``."""
        return self.payload[index]

    def u16(self, index: int) -> int:
        """Return the big-endian 16-bit value at ``index``."""
        return int.from_bytes(self.payload[index : index + 2], "big")


def checksum(data: bytes) -> bytes:
    """Return the frame checksum over command and payload bytes."""
    return (sum(data) & 0xFFFF).to_bytes(2, "little")


def encode_frame(command: int, payload: bytes = b"") -> str:
    """Encode a request frame as hex string."""
    length = len(payload) + 1
    if length >= 255:
        length_field = bytes((0xFF, length - 255))
    else:
        length_field = bytes((length,))
    frame = FRAME_PREFIX + length_field + bytes((command,)) + payload + REQUEST_TRAILER
    return frame.hex()


def decode_frame(raw: str) -> Frame:
    """Decode and validate a response frame given as hex string."""
    try:
        data = bytes.fromhex(raw)
    except ValueError as err:
        raise OvenProtocolError(f"Frame is not hex: {raw!r}") from err
    if not data.startswith(FRAME_PREFIX):
        raise OvenProtocolError(f"Bad frame prefix: {raw!r}")
    pos = len(FRAME_PREFIX)
    if len(data) < pos + 2:
        raise OvenProtocolError(f"Frame too short: {raw!r}")
    length = data[pos]
    pos += 1
    if length == 0xFF:
        length = 255 + data[pos]
        pos += 1
    body = data[pos : pos + length]
    trailer = data[pos + length : pos + length + 2]
    if len(body) != length or len(trailer) != 2:
        raise OvenProtocolError(f"Frame length mismatch: {raw!r}")
    if trailer != checksum(body):
        raise OvenProtocolError(f"Frame checksum mismatch: {raw!r}")
    return Frame(command=body[0], payload=body[1:])


def _require(frame: Frame, size: int) -> None:
    if len(frame.payload) < size:
        raise OvenProtocolError(
            f"Payload of command {frame.command:02x} too short: "
            f"{len(frame.payload)} < {size}"
        )


@dataclass(frozen=True, slots=True)
class Status:
    """Live status (cmd 0x00)."""

    water: bool
    phase: int
    door_open: bool
    temperature: int
    flap: int
    burn_minutes: int
    alarm: int
    relay: bool
    alarm2: int
    flap_pos: int
    boiler_temp: int | None = None
    buffer_top_temp: int | None = None
    buffer_bottom_temp: int | None = None
    pump: bool | None = None

    @classmethod
    def from_frame(cls, frame: Frame) -> Status:
        """Decode a status frame."""
        _require(frame, 10)
        # The command byte of the response marks the water-heating variant.
        water = frame.command == 0x01
        flap = frame.u8(3)
        if flap > 100:
            flap -= 150
        extra: dict[str, Any] = {}
        if water:
            _require(frame, 14)
            extra = {
                "boiler_temp": _water_temp(frame.u8(10)),
                "buffer_top_temp": _water_temp(frame.u8(11)),
                "pump": frame.u8(12) == 1,
                "buffer_bottom_temp": _water_temp(frame.u8(13)),
            }
        return cls(
            water=water,
            phase=frame.u8(0) & 0x0F,
            door_open=(frame.u8(0) >> 4) in (1, 3),
            temperature=frame.u16(1),
            flap=flap,
            burn_minutes=frame.u8(4) * 60 + frame.u8(5),
            alarm=frame.u8(6),
            relay=frame.u8(7) == 1,
            alarm2=frame.u8(8),
            flap_pos=frame.u8(9),
            **extra,
        )


def _water_temp(value: int) -> int | None:
    return None if value == NO_SENSOR else value - WATER_TEMP_OFFSET


@dataclass(frozen=True, slots=True)
class BurnSettings:
    """Stove settings (cmd 0x12, written with 0x13)."""

    manufacturer: int
    model: int
    close_timeout: int
    relay_mode: int
    alarm_temp: int
    start_temp: int
    interval: int

    @classmethod
    def from_frame(cls, frame: Frame) -> BurnSettings:
        """Decode a stove settings frame."""
        _require(frame, 10)
        return cls(
            manufacturer=frame.u8(0),
            model=frame.u8(1),
            close_timeout=frame.u8(2),
            relay_mode=frame.u8(3),
            alarm_temp=frame.u16(4),
            start_temp=frame.u16(6),
            interval=frame.u16(8),
        )

    def to_payload(self) -> bytes:
        """Encode for cmd 0x13."""
        return (
            bytes((self.manufacturer, self.model, self.close_timeout, self.relay_mode))
            + self.alarm_temp.to_bytes(2, "big")
            + self.start_temp.to_bytes(2, "big")
            + self.interval.to_bytes(2, "big")
        )


@dataclass(frozen=True, slots=True)
class WaterSettings:
    """Pump settings of the water-heating variant (cmd 0x20, written with 0x21)."""

    pump_on_temp: int
    pump_off_hysteresis: int
    boiler_sensor: int

    @classmethod
    def from_frame(cls, frame: Frame) -> WaterSettings:
        """Decode a water settings frame."""
        _require(frame, 3)
        return cls(
            pump_on_temp=frame.u8(0),
            pump_off_hysteresis=frame.u8(1),
            boiler_sensor=frame.u8(2),
        )

    def to_payload(self) -> bytes:
        """Encode for cmd 0x21."""
        return bytes((self.pump_on_temp, self.pump_off_hysteresis, self.boiler_sensor))


@dataclass(frozen=True, slots=True)
class BurnParams:
    """Burn curve (cmd 0x30, written with 0x31)."""

    alarm_temp: int
    start_temp: int
    flap2: int
    temp3: int
    flap3: int
    temp4: int
    flap4: int
    temp5: int
    flap5: int
    close_timeout: int
    phase2_min: int

    @classmethod
    def from_frame(cls, frame: Frame) -> BurnParams:
        """Decode a burn curve frame."""
        _require(frame, 13)
        return cls(
            alarm_temp=frame.u16(0),
            start_temp=frame.u16(2),
            flap2=frame.u8(4),
            temp3=frame.u8(5),
            flap3=frame.u8(6),
            temp4=frame.u8(7),
            flap4=frame.u8(8),
            temp5=frame.u8(9),
            flap5=frame.u8(10),
            close_timeout=frame.u8(11),
            phase2_min=frame.u8(12),
        )

    def to_payload(self) -> bytes:
        """Encode for cmd 0x31."""
        return (
            self.alarm_temp.to_bytes(2, "big")
            + self.start_temp.to_bytes(2, "big")
            + bytes(
                (
                    self.flap2,
                    self.temp3,
                    self.flap3,
                    self.temp4,
                    self.flap4,
                    self.temp5,
                    self.flap5,
                    self.close_timeout,
                    self.phase2_min,
                )
            )
        )


@dataclass(frozen=True, slots=True)
class DeviceClock:
    """Controller clock (cmd 0x22). ``flags`` 1 is most likely summer time."""

    time: datetime | None
    flags: int

    @classmethod
    def from_frame(cls, frame: Frame) -> DeviceClock:
        """Decode a clock frame."""
        _require(frame, 5)
        month = frame.u8(1)
        flags = 2 if month > 32 else 1 if month > 16 else 0
        month -= 16 * flags
        try:
            time = datetime(
                2000 + frame.u8(0), month, frame.u8(2), frame.u8(3), frame.u8(4)
            )
        except ValueError:
            time = None
        return cls(time=time, flags=flags)


@dataclass(frozen=True, slots=True)
class McuInfo:
    """MCU firmware (cmd 0x24)."""

    version: int
    build: int

    @classmethod
    def from_frame(cls, frame: Frame) -> McuInfo:
        """Decode an MCU info frame."""
        _require(frame, 4)
        return cls(version=frame.u8(1), build=frame.u16(2))


@dataclass(frozen=True, slots=True)
class AlarmRecord:
    """One entry of the alarm log (cmd 0x04)."""

    day: date | None
    type: int
    value: int

    @property
    def name(self) -> str:
        """Return a key for the alarm type."""
        return ALARM_LOG_TYPES.get(self.type, f"unknown_{self.type}")


def decode_alarm_log(frame: Frame) -> list[AlarmRecord]:
    """Decode the alarm log. The log is a ring buffer; records are not sorted."""
    records = []
    for index in range(ALARM_LOG_RECORDS):
        base = index * ALARM_LOG_RECORD_SIZE
        chunk = frame.payload[base : base + ALARM_LOG_RECORD_SIZE]
        if len(chunk) < ALARM_LOG_RECORD_SIZE:
            break
        if chunk[0] == 0:
            continue
        try:
            day = date(2000 + chunk[0], chunk[1] % 16, chunk[2])
        except ValueError:
            day = None
        records.append(
            AlarmRecord(
                day=day, type=chunk[3], value=int.from_bytes(chunk[4:6], "big")
            )
        )
    return records


class OvenClient:
    """Async client for one controller."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        timeout: float = 15,
        attempts: int = 5,
        retry_delay: float = 1.0,
        request_gap: float = 0.3,
    ) -> None:
        """Initialise the client. ``host`` is an IP address or host name."""
        self._session = session
        self._base_url = host if host.startswith("http") else f"http://{host}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._attempts = attempts
        self._retry_delay = retry_delay
        self._request_gap = request_gap
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the base URL."""
        return self._base_url

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{self._base_url}{path}"
        data = None if body is None else json.dumps(body)
        async with self._lock:
            last_error: Exception | None = None
            for attempt in range(1, self._attempts + 1):
                try:
                    async with self._session.request(
                        method,
                        url,
                        data=data,
                        headers={"Content-Type": "text/plain"},
                        timeout=self._timeout,
                    ) as resp:
                        resp.raise_for_status()
                        text = await resp.text()
                    break
                except (aiohttp.ClientError, TimeoutError) as err:
                    last_error = err
                    _LOGGER.debug(
                        "%s %s failed (attempt %s/%s): %s",
                        method,
                        path,
                        attempt,
                        self._attempts,
                        err,
                    )
                    if attempt < self._attempts:
                        await asyncio.sleep(self._retry_delay)
            else:
                raise OvenConnectionError(
                    f"{method} {path} failed: {last_error}"
                ) from last_error
            await asyncio.sleep(self._request_gap)
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            # Never include the body: /module/config contains Wi-Fi keys.
            raise OvenProtocolError(f"{path} did not return JSON") from err

    async def _direct(self, command: int, payload: bytes | None = None) -> Frame:
        path = f"/direct/{command:02x}"
        if payload is None:
            result = await self._request("GET", path)
        else:
            result = await self._request(
                "POST", path, {"raw": encode_frame(command, payload)}
            )
        if not isinstance(result, dict) or not isinstance(result.get("raw"), str):
            raise OvenProtocolError(f"{path} returned no frame")
        return decode_frame(result["raw"])

    async def get_status(self) -> Status:
        """Read the live status."""
        return Status.from_frame(await self._direct(CMD_STATUS))

    async def get_alarm_log(self) -> list[AlarmRecord]:
        """Read the alarm log."""
        return decode_alarm_log(await self._direct(CMD_ALARM_LOG))

    async def get_burn_settings(self) -> BurnSettings:
        """Read the stove settings."""
        return BurnSettings.from_frame(await self._direct(CMD_BURN_SETTINGS))

    async def set_burn_settings(self, settings: BurnSettings) -> BurnSettings:
        """Write the stove settings; returns what the controller reports back."""
        frame = await self._direct(CMD_SET_BURN_SETTINGS, settings.to_payload())
        return BurnSettings.from_frame(frame)

    async def get_water_settings(self) -> WaterSettings:
        """Read the pump settings (water variant)."""
        return WaterSettings.from_frame(await self._direct(CMD_WATER_SETTINGS))

    async def set_water_settings(self, settings: WaterSettings) -> WaterSettings:
        """Write the pump settings (water variant)."""
        frame = await self._direct(CMD_SET_WATER_SETTINGS, settings.to_payload())
        return WaterSettings.from_frame(frame)

    async def get_burn_params(self) -> BurnParams:
        """Read the burn curve."""
        return BurnParams.from_frame(await self._direct(CMD_BURN_PARAMS))

    async def set_burn_params(self, params: BurnParams) -> BurnParams:
        """Write the burn curve; returns what the controller reports back."""
        frame = await self._direct(CMD_SET_BURN_PARAMS, params.to_payload())
        return BurnParams.from_frame(frame)

    async def get_alarm_mask(self) -> int:
        """Read the alarm mask (bits ``ALARM_*``)."""
        frame = await self._direct(CMD_ALARM_MASK)
        _require(frame, 1)
        return frame.u8(0) & ALARM_MASK_BITS

    async def set_alarm_mask(self, mask: int) -> None:
        """Write the alarm mask."""
        await self._direct(CMD_SET_ALARM_MASK, bytes((mask & ALARM_MASK_BITS, 0)))

    async def get_clock(self) -> DeviceClock:
        """Read the controller clock."""
        return DeviceClock.from_frame(await self._direct(CMD_CLOCK))

    async def set_clock(self, now: datetime) -> None:
        """Set the controller clock to the given local time."""
        payload = bytes((now.year - 2000, now.month, now.day, now.hour, now.minute))
        await self._direct(CMD_SET_CLOCK, payload)

    async def get_mcu_info(self) -> McuInfo:
        """Read the MCU firmware version."""
        return McuInfo.from_frame(await self._direct(CMD_MCU_INFO))

    async def get_module_state(self) -> dict[str, Any]:
        """Read the Wi-Fi module state (contains ``device-id``)."""
        result = await self._request("GET", "/module/state")
        if not isinstance(result, dict):
            raise OvenProtocolError("/module/state returned no object")
        return result
