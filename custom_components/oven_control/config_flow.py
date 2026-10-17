"""Config flow for Oven Control."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import OvenClient, OvenConnectionError, OvenError
from .const import (
    CONF_SETTINGS_INTERVAL,
    CONF_STATUS_INTERVAL,
    DEFAULT_SETTINGS_INTERVAL,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    MAX_SETTINGS_INTERVAL,
    MAX_STATUS_INTERVAL,
    MIN_SETTINGS_INTERVAL,
    MIN_STATUS_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_STATUS_INTERVAL, default=DEFAULT_STATUS_INTERVAL
        ): NumberSelector(
            NumberSelectorConfig(
                min=MIN_STATUS_INTERVAL,
                max=MAX_STATUS_INTERVAL,
                step=1,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_SETTINGS_INTERVAL, default=DEFAULT_SETTINGS_INTERVAL
        ): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SETTINGS_INTERVAL,
                max=MAX_SETTINGS_INTERVAL,
                step=1,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)


class OvenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a controller by host name or IP address."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OvenOptionsFlow:
        """Return the options flow."""
        return OvenOptionsFlow()

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


class OvenOptionsFlow(OptionsFlowWithReload):
    """Polling intervals; the entry reloads when they change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the intervals."""
        if user_input is not None:
            return self.async_create_entry(
                data={key: int(value) for key, value in user_input.items()}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
