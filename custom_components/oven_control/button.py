"""Buttons for Oven Control."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import OvenConfigEntry, OvenSettingsCoordinator
from .entity import OvenEntity, async_write

PARALLEL_UPDATES = 1

# Like the vendor app, only set the clock while no fire is being controlled:
# flap closed, or one of the start phases.
CLOCK_SAFE_PHASES = (0, 1, 2)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OvenConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    runtime = entry.runtime_data
    async_add_entities([OvenSyncClockButton(runtime.settings, runtime, "sync_clock")])


class OvenSyncClockButton(OvenEntity[OvenSettingsCoordinator], ButtonEntity):
    """Set the controller clock to the Home Assistant time."""

    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        """Set the clock."""
        status = self.runtime.status.data
        if status.flap != 0 and status.phase not in CLOCK_SAFE_PHASES:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="burn_in_progress"
            )
        await async_write(self.runtime.client.set_clock(dt_util.now()))
        await self.coordinator.async_request_refresh()
