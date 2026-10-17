"""Config flow for Oven Control."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OvenClient, OvenConnectionError, OvenError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class OvenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a controller by host name or IP address."""

    VERSION = 1

    async def _async_probe(self, host: str) -> tuple[str | None, dict[str, str]]:
        """Return the device id at ``host``, or form errors."""
        client = OvenClient(async_get_clientsession(self.hass), host)
        try:
            state = await client.get_module_state()
            await client.get_status()
        except OvenConnectionError:
            return None, {"base": "cannot_connect"}
        except OvenError:
            return None, {"base": "not_supported"}
        except Exception:
            _LOGGER.exception("Unexpected error while probing %s", host)
            return None, {"base": "unknown"}
        device_id = state.get("device-id")
        if not isinstance(device_id, str) or not device_id:
            return None, {"base": "not_supported"}
        return device_id, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device_id, errors = await self._async_probe(host)
            if device_id:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title="Oven", data={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host of an existing entry, e.g. after a DHCP change."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            device_id, errors = await self._async_probe(host)
            if device_id:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or dict(entry.data)
            ),
            errors=errors,
        )
