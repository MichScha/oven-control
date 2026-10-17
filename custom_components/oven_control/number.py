"""Number entities for the burn curve and pump settings of Oven Control."""

from __future__ import annotations

from dataclasses import dataclass, replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OvenConfigEntry, OvenRuntimeData, OvenSettingsCoordinator
from .entity import OvenEntity, async_write

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OvenNumberDescription(NumberEntityDescription):
    """Number backed by one field of a settings block.

    ``block`` is ``burn_params`` (cmd 0x30/0x31) or ``water_settings`` (0x20/0x21);
    ``field`` is the attribute of that block. Ranges are the ones of the vendor app.
    """

    block: str
    field: str


def _temp(key: str, field: str, low: int, high: int, step: int = 1, block: str = "burn_params") -> OvenNumberDescription:
    return OvenNumberDescription(
        key=key,
        translation_key=key,
        block=block,
        field=field,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=low,
        native_max_value=high,
        native_step=step,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


def _percent(key: str, field: str, low: int, high: int, step: int) -> OvenNumberDescription:
    return OvenNumberDescription(
        key=key,
        translation_key=key,
        block="burn_params",
        field=field,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=low,
        native_max_value=high,
        native_step=step,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
    )


def _minutes(key: str, field: str, low: int, high: int, step: int) -> OvenNumberDescription:
    return OvenNumberDescription(
        key=key,
        translation_key=key,
        block="burn_params",
        field=field,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=low,
        native_max_value=high,
        native_step=step,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


BURN_NUMBERS: tuple[OvenNumberDescription, ...] = (
    _temp("start_temp", "start_temp", 55, 995, 5),
    _percent("flap2", "flap2", 5, 100, 5),
    _percent("temp3", "temp3", 5, 95, 1),
    _percent("flap3", "flap3", 5, 100, 5),
    _percent("temp4", "temp4", 5, 95, 1),
    _percent("flap4", "flap4", 5, 100, 5),
    _percent("temp5", "temp5", 5, 95, 1),
    _percent("flap5", "flap5", 5, 100, 5),
    _minutes("phase2_min", "phase2_min", 1, 30, 1),
    _minutes("close_timeout", "close_timeout", 0, 90, 5),
)

WATER_NUMBERS: tuple[OvenNumberDescription, ...] = (
    _temp("pump_on_temp", "pump_on_temp", 55, 70, block="water_settings"),
    _temp("pump_off_hysteresis", "pump_off_hysteresis", 2, 15, block="water_settings"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers."""
    runtime = entry.runtime_data
    descriptions = BURN_NUMBERS + (WATER_NUMBERS if runtime.water else ())
    async_add_entities(
        OvenNumber(runtime.settings, runtime, description) for description in descriptions
    )


class OvenNumber(OvenEntity[OvenSettingsCoordinator], NumberEntity):
    """Number backed by one field of a settings block."""

    entity_description: OvenNumberDescription

    def __init__(
        self,
        coordinator: OvenSettingsCoordinator,
        runtime: OvenRuntimeData,
        description: OvenNumberDescription,
    ) -> None:
        """Initialise the number."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        block = getattr(self.coordinator.data, self.entity_description.block)
        return None if block is None else getattr(block, self.entity_description.field)

    async def async_set_native_value(self, value: float) -> None:
        """Write the whole block with one field changed."""
        description = self.entity_description
        data = self.coordinator.data
        block = replace(getattr(data, description.block), **{description.field: int(value)})
        client = self.runtime.client
        if description.block == "burn_params":
            result = await async_write(client.set_burn_params(block))
        else:
            result = await async_write(client.set_water_settings(block))
        self.coordinator.async_set_updated_data(replace(data, **{description.block: result}))
