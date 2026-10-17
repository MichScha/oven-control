"""The Oven Control integration (Ofen Innovativ / Firecontrols stove controllers)."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OvenClient, OvenError
from .const import DOMAIN
from .coordinator import (
    OvenConfigEntry,
    OvenRuntimeData,
    OvenSettingsCoordinator,
    OvenStatusCoordinator,
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: OvenConfigEntry) -> bool:
    """Set up a controller from a config entry."""
    client = OvenClient(async_get_clientsession(hass), entry.data[CONF_HOST])

    try:
        module_state = await client.get_module_state()
        mcu = await client.get_mcu_info()
    except OvenError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    if module_state.get("device-id") != entry.unique_id:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="wrong_device"
        )

    status = OvenStatusCoordinator(hass, entry, client)
    await status.async_config_entry_first_refresh()
    water = status.data.water

    settings = OvenSettingsCoordinator(hass, entry, client, water)
    await settings.async_config_entry_first_refresh()

    entry.runtime_data = OvenRuntimeData(
        client=client,
        device_id=entry.unique_id,
        mcu=mcu,
        water=water,
        status=status,
        settings=settings,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OvenConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
