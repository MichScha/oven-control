"""Switches for the alarm mask of Oven Control."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import (
    ALARM_BOILER_OVERHEAT,
    ALARM_BUFFER_TOP_OVERHEAT,
    ALARM_FLAME_SENSOR_ERROR,
    ALARM_HEATING_ERROR,
)
from .coordinator import OvenConfigEntry, OvenRuntimeData, OvenSettingsCoordinator
from .entity import OvenEntity, async_write

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OvenAlarmMaskDescription(SwitchEntityDescription):
    """One bit of the alarm mask (cmd 0x32/0x33)."""

    bit: int
    water_only: bool = False


ALARM_MASK_SWITCHES: tuple[OvenAlarmMaskDescription, ...] = (
    OvenAlarmMaskDescription(key="mask_heating_error", bit=ALARM_HEATING_ERROR),
    OvenAlarmMaskDescription(key="mask_flame_sensor_error", bit=ALARM_FLAME_SENSOR_ERROR),
    OvenAlarmMaskDescription(
        key="mask_boiler_overheat", bit=ALARM_BOILER_OVERHEAT, water_only=True
    ),
    OvenAlarmMaskDescription(
        key="mask_buffer_top_overheat", bit=ALARM_BUFFER_TOP_OVERHEAT, water_only=True
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    runtime = entry.runtime_data
    async_add_entities(
        OvenAlarmMaskSwitch(runtime.settings, runtime, description)
        for description in ALARM_MASK_SWITCHES
        if runtime.water or not description.water_only
    )


class OvenAlarmMaskSwitch(OvenEntity[OvenSettingsCoordinator], SwitchEntity):
    """One bit of the alarm mask, as shown in the vendor app's "Set Alarme" list."""

    entity_description: OvenAlarmMaskDescription
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: OvenSettingsCoordinator,
        runtime: OvenRuntimeData,
        description: OvenAlarmMaskDescription,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def is_on(self) -> bool:
        """Return whether the bit is set."""
        return bool(self.coordinator.data.alarm_mask & self.entity_description.bit)

    async def _async_write(self, on: bool) -> None:
        data = self.coordinator.data
        bit = self.entity_description.bit
        mask = data.alarm_mask | bit if on else data.alarm_mask & ~bit
        await async_write(self.runtime.client.set_alarm_mask(mask))
        self.coordinator.async_set_updated_data(replace(data, alarm_mask=mask))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the bit."""
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear the bit."""
        await self._async_write(False)
