"""Select entities for Oven Control."""

from __future__ import annotations

from dataclasses import replace

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BOILER_SENSORS, RELAY_MODES
from .coordinator import OvenConfigEntry, OvenSettingsCoordinator
from .entity import OvenEntity, async_write

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    runtime = entry.runtime_data
    entities: list[SelectEntity] = [
        OvenRelayModeSelect(runtime.settings, runtime, "relay_mode")
    ]
    if runtime.water:
        entities.append(OvenBoilerSensorSelect(runtime.settings, runtime, "boiler_sensor"))
    async_add_entities(entities)


class OvenRelayModeSelect(OvenEntity[OvenSettingsCoordinator], SelectEntity):
    """What the DG relay (flue-gas fan / extractor hood) does."""

    _attr_translation_key = "relay_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = RELAY_MODES

    @property
    def current_option(self) -> str | None:
        """Return the current mode."""
        mode = self.coordinator.data.burn_settings.relay_mode
        return RELAY_MODES[mode] if mode < len(RELAY_MODES) else None

    async def async_select_option(self, option: str) -> None:
        """Write the stove settings with the new relay mode."""
        data = self.coordinator.data
        settings = replace(data.burn_settings, relay_mode=RELAY_MODES.index(option))
        result = await async_write(self.runtime.client.set_burn_settings(settings))
        self.coordinator.async_set_updated_data(replace(data, burn_settings=result))


class OvenBoilerSensorSelect(OvenEntity[OvenSettingsCoordinator], SelectEntity):
    """Buffer sensor that controls the pump (water variant)."""

    _attr_translation_key = "boiler_sensor"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = BOILER_SENSORS

    @property
    def current_option(self) -> str | None:
        """Return the current sensor."""
        water = self.coordinator.data.water_settings
        if water is None or water.boiler_sensor >= len(BOILER_SENSORS):
            return None
        return BOILER_SENSORS[water.boiler_sensor]

    async def async_select_option(self, option: str) -> None:
        """Write the pump settings with the new sensor."""
        data = self.coordinator.data
        assert data.water_settings is not None
        settings = replace(data.water_settings, boiler_sensor=BOILER_SENSORS.index(option))
        result = await async_write(self.runtime.client.set_water_settings(settings))
        self.coordinator.async_set_updated_data(replace(data, water_settings=result))
