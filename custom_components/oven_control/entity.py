"""Base entity for Oven Control."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import OvenError
from .const import DOMAIN, MANUFACTURERS
from .coordinator import OvenRuntimeData
from .models import MODELS


class OvenEntity[CoordinatorT: DataUpdateCoordinator[Any]](
    CoordinatorEntity[CoordinatorT]
):
    """Entity of one controller."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CoordinatorT, runtime: OvenRuntimeData, key: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.device_id}_{key}"
        settings = runtime.settings.data.burn_settings
        mcu = runtime.mcu
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.device_id)},
            name="Oven",
            manufacturer=MANUFACTURERS.get(settings.manufacturer, "Firecontrols"),
            model=MODELS.get((settings.manufacturer, settings.model)),
            sw_version=f"{mcu.version} (build {mcu.build})",
            hw_version=runtime.settings.data.module_state.get("software-version"),
        )


async def async_write[T](call: Awaitable[T]) -> T:
    """Run a write request and turn client errors into Home Assistant errors."""
    try:
        return await call
    except OvenError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": str(err)},
        ) from err
