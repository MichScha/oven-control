"""Data update coordinators for Oven Control."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AlarmRecord,
    BurnParams,
    BurnSettings,
    DeviceClock,
    McuInfo,
    OvenClient,
    OvenError,
    Status,
    WaterSettings,
)
from .const import DOMAIN, SETTINGS_INTERVAL, STATUS_INTERVAL

_LOGGER = logging.getLogger(__name__)

type OvenConfigEntry = ConfigEntry[OvenRuntimeData]


@dataclass(frozen=True, slots=True)
class OvenSettings:
    """Slowly changing data, read every few minutes."""

    burn_params: BurnParams
    burn_settings: BurnSettings
    water_settings: WaterSettings | None
    alarm_mask: int
    clock: DeviceClock
    alarm_log: list[AlarmRecord]
    module_state: dict[str, Any]


@dataclass(slots=True)
class OvenRuntimeData:
    """Objects shared by the platforms of one config entry."""

    client: OvenClient
    device_id: str
    mcu: McuInfo
    water: bool
    status: OvenStatusCoordinator
    settings: OvenSettingsCoordinator


class OvenStatusCoordinator(DataUpdateCoordinator[Status]):
    """Polls the live status."""

    config_entry: OvenConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: OvenConfigEntry, client: OvenClient
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} status",
            update_interval=STATUS_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> Status:
        try:
            return await self.client.get_status()
        except OvenError as err:
            raise UpdateFailed(str(err)) from err


class OvenSettingsCoordinator(DataUpdateCoordinator[OvenSettings]):
    """Polls settings, clock, alarm log and module state."""

    config_entry: OvenConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OvenConfigEntry,
        client: OvenClient,
        water: bool,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} settings",
            update_interval=SETTINGS_INTERVAL,
        )
        self.client = client
        self.water = water

    async def _async_update_data(self) -> OvenSettings:
        client = self.client
        try:
            return OvenSettings(
                burn_params=await client.get_burn_params(),
                burn_settings=await client.get_burn_settings(),
                water_settings=(
                    await client.get_water_settings() if self.water else None
                ),
                alarm_mask=await client.get_alarm_mask(),
                clock=await client.get_clock(),
                alarm_log=await client.get_alarm_log(),
                module_state=await client.get_module_state(),
            )
        except OvenError as err:
            raise UpdateFailed(str(err)) from err
