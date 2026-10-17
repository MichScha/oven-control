"""Tests for the protocol client."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any

import aiohttp
import pytest

from custom_components.oven_control.api import (
    ALARM_FLAME_SENSOR_ERROR,
    ALARM_HEATING_ERROR,
    BurnParams,
    BurnSettings,
    OvenClient,
    OvenConnectionError,
    OvenProtocolError,
    Status,
    decode_alarm_log,
    decode_frame,
    encode_frame,
)

from . import frames


class FakeResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body
        self.status = status

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)  # type: ignore[arg-type]

    async def text(self) -> str:
        return self._body


class FakeSession:
    """Answers requests from a path -> list of answers table."""

    def __init__(self, answers: dict[str, list[Any]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        path = url.split("://", 1)[1].split("/", 1)[1]
        self.calls.append((method, "/" + path, kwargs.get("data")))
        answer = self.answers["/" + path].pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, str) and answer.startswith("aacc3355"):
            return FakeResponse(json.dumps({"raw": answer}))
        return FakeResponse(answer if isinstance(answer, str) else json.dumps(answer))


def make_client(answers: dict[str, list[Any]]) -> tuple[OvenClient, FakeSession]:
    session = FakeSession(answers)
    client = OvenClient(session, "192.0.2.10", retry_delay=0, request_gap=0)  # type: ignore[arg-type]
    return client, session


def test_decode_status() -> None:
    status = Status.from_frame(decode_frame(frames.STATUS))
    assert status == Status(
        water=False,
        phase=1,
        door_open=False,
        temperature=93,
        flap=100,
        burn_minutes=3,
        alarm=40,
        relay=False,
        alarm2=2,
        flap_pos=19,
    )
    stopped = Status.from_frame(decode_frame(frames.STATUS_STOPPED))
    assert stopped.phase == 8
    assert stopped.alarm & ALARM_HEATING_ERROR
    assert not stopped.alarm & ALARM_FLAME_SENSOR_ERROR
    assert stopped.burn_minutes == 46


def test_decode_water_status() -> None:
    status = Status.from_frame(decode_frame(frames.water_status()))
    assert status.water
    assert status.phase == 3
    assert status.temperature == 512
    assert status.flap == 60
    assert status.burn_minutes == 85
    assert status.boiler_temp == 60
    assert status.buffer_top_temp == 50
    assert status.pump is True
    assert status.buffer_bottom_temp is None


def test_decode_settings() -> None:
    assert BurnSettings.from_frame(decode_frame(frames.BURN_SETTINGS)) == BurnSettings(
        manufacturer=8,
        model=1,
        close_timeout=5,
        relay_mode=0,
        alarm_temp=1200,
        start_temp=205,
        interval=480,
    )
    assert BurnParams.from_frame(decode_frame(frames.BURN_PARAMS)) == BurnParams(
        alarm_temp=1200,
        start_temp=205,
        flap2=50,
        temp3=90,
        flap3=40,
        temp4=75,
        flap4=30,
        temp5=59,
        flap5=15,
        close_timeout=5,
        phase2_min=15,
    )


def test_decode_alarm_log() -> None:
    records = decode_alarm_log(decode_frame(frames.ALARM_LOG))
    assert len(records) == 41
    assert records[0].day == date(2017, 3, 1)
    assert records[0].name == "flame_sensor_error"
    assert {r.name for r in records} >= {"unknown_16", "unknown_17", "heating_error"}
    assert any(r.day == date(2025, 11, 23) and r.name == "heating_error" for r in records)


def test_encode_frame_matches_app() -> None:
    # Frames built by the vendor app for the same values.
    params = BurnParams.from_frame(decode_frame(frames.BURN_PARAMS))
    assert encode_frame(0x31, params.to_payload()) == (
        "aacc33550e3104b000cd325a284b1e3b0f050fffff"
    )
    settings = BurnSettings.from_frame(decode_frame(frames.BURN_SETTINGS))
    assert encode_frame(0x13, settings.to_payload()) == (
        "aacc33550b130801050004b000cd01e0ffff"
    )
    assert encode_frame(0x35, b"\x00") == "aacc33550235" + "00ffff"


def test_encode_long_frame_roundtrip() -> None:
    payload = bytes(range(256)) + bytes(100)
    raw = encode_frame(0x04, payload)
    assert raw[8:12] == "ff66"
    # Replace the request trailer by the checksum a device would send.
    body = bytes.fromhex(raw[12:-4])
    raw = raw[:-4] + (sum(body) & 0xFFFF).to_bytes(2, "little").hex()
    frame = decode_frame(raw)
    assert frame.command == 0x04
    assert frame.payload == payload


@pytest.mark.parametrize(
    "raw",
    [
        "zz",
        "bbcc33550f00",
        "aacc33550f0001005d64000328000213ffff01ff0005",  # checksum
        "aacc33550f0001005d6400",  # truncated
    ],
)
def test_decode_frame_rejects(raw: str) -> None:
    with pytest.raises(OvenProtocolError):
        decode_frame(raw)


async def test_client_reads() -> None:
    client, session = make_client(
        {
            "/direct/00": [frames.STATUS],
            "/direct/22": [frames.CLOCK],
            "/direct/24": [frames.MCU_INFO],
            "/direct/32": [frames.ALARM_MASK],
            "/module/state": [frames.MODULE_STATE],
        }
    )
    assert (await client.get_status()).temperature == 93
    clock = await client.get_clock()
    assert clock.time == datetime(2026, 10, 17, 20, 32)
    assert clock.flags == 1
    mcu = await client.get_mcu_info()
    assert (mcu.version, mcu.build) == (32, 283)
    assert await client.get_alarm_mask() == 0
    assert (await client.get_module_state())["device-id"] == frames.MODULE_STATE["device-id"]
    assert [c[0] for c in session.calls] == ["GET"] * 5


async def test_client_write_sends_frame() -> None:
    params = BurnParams.from_frame(decode_frame(frames.BURN_PARAMS))
    client, session = make_client({"/direct/31": [frames.BURN_PARAMS]})
    assert await client.set_burn_params(params) == params
    method, path, data = session.calls[0]
    assert (method, path) == ("POST", "/direct/31")
    assert json.loads(data) == {"raw": "aacc33550e3104b000cd325a284b1e3b0f050fffff"}


async def test_client_set_clock() -> None:
    client, session = make_client({"/direct/23": [frames.CLOCK]})
    await client.set_clock(datetime(2026, 10, 17, 20, 32))
    assert json.loads(session.calls[0][2]) == {"raw": "aacc335506231a0a111420ffff"}


async def test_client_retries_on_reset() -> None:
    reset = aiohttp.ClientOSError(104, "Connection reset by peer")
    client, session = make_client({"/direct/00": [reset, reset, frames.STATUS]})
    assert (await client.get_status()).phase == 1
    assert len(session.calls) == 3


async def test_client_gives_up() -> None:
    reset = aiohttp.ClientOSError(104, "Connection reset by peer")
    client, _ = make_client({"/direct/00": [reset] * 5})
    with pytest.raises(OvenConnectionError):
        await client.get_status()


async def test_client_rejects_garbage() -> None:
    client, _ = make_client({"/direct/00": ["not json"], "/direct/12": [{"foo": 1}]})
    with pytest.raises(OvenProtocolError):
        await client.get_status()
    with pytest.raises(OvenProtocolError):
        await client.get_burn_settings()
