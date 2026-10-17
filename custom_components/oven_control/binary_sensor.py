"""Binary sensors for Oven Control."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import (
    ALARM_BOILER_OVERHEAT,
    ALARM_BUFFER_TOP_OVERHEAT,
    ALARM_FLAME_SENSOR_ERROR,
    ALARM_HEATING_ERROR,
    Status,
)
from .coordinator import (
    OvenConfigEntry,
    OvenRuntimeData,
    OvenSettingsCoordinator,
    OvenStatusCoordinator,
)
from .entity import OvenEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OvenBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor fed by the live status."""

    value_fn: Callable[[Status], bool | None]
    water_only: bool = False


def _alarm(key: str, bit: int, water_only: bool = False) -> OvenBinarySensorDescription:
    return OvenBinarySensorDescription(
        key=key,
        translation_key=key,
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: bool(s.alarm & bit),
        water_only=water_only,
    )


STATUS_BINARY_SENSORS: tuple[OvenBinarySensorDescription, ...] = (
    OvenBinarySensorDescription(
        key="door",
        translation_key="door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: s.door_open,
    ),
    OvenBinarySensorDescription(
        key="relay",
        translation_key="relay",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.relay,
    ),
    OvenBinarySensorDescription(
        key="pump",
        translation_key="pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.pump,
        water_only=True,
    ),
    _alarm("heating_error", ALARM_HEATING_ERROR),
    _alarm("flame_sensor_error", ALARM_FLAME_SENSOR_ERROR),
    # Always set on units without water sensors, so only created for the water variant.
    _alarm("boiler_overheat", ALARM_BOILER_OVERHEAT, water_only=True),
    _alarm("buffer_top_overheat", ALARM_BUFFER_TOP_OVERHEAT, water_only=True),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        OvenStatusBinarySensor(runtime.status, runtime, description)
        for description in STATUS_BINARY_SENSORS
        if runtime.water or not description.water_only
    ]
    entities.append(OvenWifiBinarySensor(runtime.settings, runtime, "wifi"))
    async_add_entities(entities)


class OvenStatusBinarySensor(OvenEntity[OvenStatusCoordinator], BinarySensorEntity):
    """Binary sensor fed by the live status."""

    entity_description: OvenBinarySensorDescription

    def __init__(
        self,
        coordinator: OvenStatusCoordinator,
        runtime: OvenRuntimeData,
        description: OvenBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class OvenWifiBinarySensor(OvenEntity[OvenSettingsCoordinator], BinarySensorEntity):
    """Whether the Wi-Fi module is connected to the home network."""

    _attr_translation_key = "wifi"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.coordinator.data.module_state.get("wifi-state") == "connected"
