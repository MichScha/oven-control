"""Sensors for Oven Control."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Status
from .coordinator import (
    OvenConfigEntry,
    OvenRuntimeData,
    OvenSettings,
    OvenSettingsCoordinator,
    OvenStatusCoordinator,
)
from .entity import OvenEntity

PARALLEL_UPDATES = 0

RECENT_ALARMS = 10


@dataclass(frozen=True, kw_only=True)
class OvenStatusSensorDescription(SensorEntityDescription):
    """Sensor fed by the live status."""

    value_fn: Callable[[Status], int | None]
    water_only: bool = False


def _water_temp(key: str, fn: Callable[[Status], int | None]) -> OvenStatusSensorDescription:
    return OvenStatusSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=fn,
        water_only=True,
    )


STATUS_SENSORS: tuple[OvenStatusSensorDescription, ...] = (
    OvenStatusSensorDescription(
        key="temperature",
        translation_key="flame_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature,
    ),
    OvenStatusSensorDescription(
        key="flap",
        translation_key="flap",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.flap,
    ),
    OvenStatusSensorDescription(
        key="phase",
        translation_key="phase",
        value_fn=lambda s: s.phase,
    ),
    OvenStatusSensorDescription(
        key="burn_duration",
        translation_key="burn_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: s.burn_minutes,
    ),
    OvenStatusSensorDescription(
        key="alarm",
        translation_key="alarm",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.alarm,
    ),
    OvenStatusSensorDescription(
        key="alarm2",
        translation_key="alarm2",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.alarm2,
    ),
    OvenStatusSensorDescription(
        key="flap_pos",
        translation_key="flap_pos",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.flap_pos,
    ),
    _water_temp("boiler_temp", lambda s: s.boiler_temp),
    _water_temp("buffer_top_temp", lambda s: s.buffer_top_temp),
    _water_temp("buffer_bottom_temp", lambda s: s.buffer_bottom_temp),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    runtime = entry.runtime_data
    entities: list[SensorEntity] = [
        OvenStatusSensor(runtime.status, runtime, description)
        for description in STATUS_SENSORS
        if runtime.water or not description.water_only
    ]
    entities += [
        OvenLatestAlarmSensor(runtime.settings, runtime, "latest_alarm"),
        OvenClockSensor(runtime.settings, runtime, "device_clock"),
    ]
    async_add_entities(entities)


class OvenStatusSensor(OvenEntity[OvenStatusCoordinator], SensorEntity):
    """Sensor fed by the live status."""

    entity_description: OvenStatusSensorDescription

    def __init__(
        self,
        coordinator: OvenStatusCoordinator,
        runtime: OvenRuntimeData,
        description: OvenStatusSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)


class OvenLatestAlarmSensor(OvenEntity[OvenSettingsCoordinator], SensorEntity):
    """Date of the most recent alarm log entry; recent entries as attributes."""

    _attr_translation_key = "latest_alarm"
    _attr_device_class = SensorDeviceClass.DATE

    def _sorted(self) -> list[Any]:
        data: OvenSettings = self.coordinator.data
        return sorted(
            (r for r in data.alarm_log if r.day is not None),
            key=lambda r: r.day,
            reverse=True,
        )

    @property
    def native_value(self) -> date | None:
        """Return the date of the newest entry."""
        records = self._sorted()
        return records[0].day if records else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the newest entries."""
        records = self._sorted()
        return {
            "alarm": records[0].name if records else None,
            "recent": [
                {"date": r.day.isoformat(), "alarm": r.name, "value": r.value}
                for r in records[:RECENT_ALARMS]
            ],
        }


class OvenClockSensor(OvenEntity[OvenSettingsCoordinator], SensorEntity):
    """Clock of the controller."""

    _attr_translation_key = "device_clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> datetime | None:
        """Return the controller time, interpreted in the local time zone."""
        time = self.coordinator.data.clock.time
        if time is None:
            return None
        return time.replace(tzinfo=dt_util.get_default_time_zone())
