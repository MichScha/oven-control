"""Diagnostics for Oven Control."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import OvenConfigEntry

TO_REDACT = {CONF_HOST, "wifi-client-ip", "wifi-client-ssid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OvenConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    settings = asdict(runtime.settings.data)
    settings["module_state"] = async_redact_data(settings["module_state"], TO_REDACT)
    # Keys containing Wi-Fi keys must never leave the device.
    settings["module_state"] = {
        k: v for k, v in settings["module_state"].items() if "psk" not in k
    }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "water": runtime.water,
        "mcu": asdict(runtime.mcu),
        "status": asdict(runtime.status.data),
        "settings": settings,
    }
