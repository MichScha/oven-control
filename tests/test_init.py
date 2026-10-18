"""Tests for setup, entities and writes."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.oven_control.api import OvenConnectionError, Status
from custom_components.oven_control.const import DEFAULT_STATUS_INTERVAL, DOMAIN
from custom_components.oven_control.diagnostics import (
    async_get_config_entry_diagnostics,
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import DEVICE_ID

STATUS_INTERVAL = timedelta(seconds=DEFAULT_STATUS_INTERVAL)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    assert mock_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), mock_entry.entry_id
    )
    assert device is not None
    assert device.manufacturer == "OFEN INNOVATIV"
    assert device.model == "SMM"
    assert device.sw_version == "32 (build 283)"
    assert device.hw_version == "1.3.2 (2022-12-05)"

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    mock_client.get_module_state.side_effect = OvenConnectionError("reset")
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_wrong_device(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    mock_client.get_module_state.return_value = {"device-id": "other"}
    mock_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_entry.entry_id)
    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


async def test_entities(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    assert hass.states.get("sensor.oven_flame_temperature").state == "93"
    assert hass.states.get("sensor.oven_air_flap").state == "100"
    phase = hass.states.get("sensor.oven_burn_phase")
    assert phase.state == "start"
    assert phase.attributes["raw_phase"] == 1
    assert hass.states.get("sensor.oven_burn_duration").state == "3"
    assert hass.states.get("binary_sensor.oven_door").state == STATE_OFF
    assert hass.states.get("binary_sensor.oven_heating_error").state == STATE_OFF
    assert hass.states.get("binary_sensor.oven_wi_fi").state == STATE_ON
    assert hass.states.get("number.oven_ts_start_temperature").state == "205"
    assert hass.states.get("number.oven_s2_flap_in_stage_2").state == "50"
    assert hass.states.get("select.oven_relay_mode").state == "off"
    assert hass.states.get("sensor.oven_device_clock") is not None

    latest = hass.states.get("sensor.oven_latest_alarm")
    assert latest.state == "2025-11-23"
    assert latest.attributes["alarm"] == "heating_error"
    assert len(latest.attributes["recent"]) == 10

    # Water-only entities are not created for this unit.
    assert hass.states.get("sensor.oven_boiler_temperature_t2") is None
    assert hass.states.get("binary_sensor.oven_circulation_pump") is None
    assert hass.states.get("select.oven_pump_control_sensor") is None

    # Alarm mask switches exist but are disabled by default.
    entry = er.async_get(hass).async_get("switch.oven_alarm_heating_error")
    assert entry is not None and entry.disabled


@pytest.mark.parametrize("water", [True])
async def test_water_entities(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    assert hass.states.get("sensor.oven_boiler_temperature_t2").state == "60"
    assert hass.states.get("sensor.oven_buffer_bottom_temperature_t7").state == "unknown"
    assert hass.states.get("binary_sensor.oven_circulation_pump").state == STATE_ON
    assert hass.states.get("select.oven_pump_control_sensor").state == "t4_top"
    assert hass.states.get("number.oven_pump_on_temperature").state == "55"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.oven_pump_control_sensor", ATTR_OPTION: "t7_bottom"},
        blocking=True,
    )
    assert mock_client.set_water_settings.call_args.args[0].boiler_sensor == 1

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.oven_pump_on_temperature", ATTR_VALUE: 60},
        blocking=True,
    )
    assert mock_client.set_water_settings.call_args.args[0].pump_on_temp == 60


async def test_status_unavailable_and_recovery(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, mock_entry)
    mock_client.get_status.side_effect = OvenConnectionError("reset")
    freezer.tick(STATUS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.oven_flame_temperature").state == STATE_UNAVAILABLE

    mock_client.get_status.side_effect = None
    mock_client.get_status.return_value = replace(
        mock_client.get_status.return_value, temperature=400, door_open=True
    )
    freezer.tick(STATUS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.oven_flame_temperature").state == "400"
    assert hass.states.get("binary_sensor.oven_door").state == STATE_ON


async def test_set_number(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.oven_s2_flap_in_stage_2", ATTR_VALUE: 65},
        blocking=True,
    )
    written = mock_client.set_burn_params.call_args.args[0]
    assert written.flap2 == 65
    # The rest of the block is written unchanged.
    assert written.start_temp == 205 and written.phase2_min == 15
    assert hass.states.get("number.oven_s2_flap_in_stage_2").state == "65"


async def test_set_number_fails(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    mock_client.set_burn_params.side_effect = OvenConnectionError("reset")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.oven_s2_flap_in_stage_2", ATTR_VALUE: 65},
            blocking=True,
        )
    assert hass.states.get("number.oven_s2_flap_in_stage_2").state == "50"


async def test_select_relay_mode(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.oven_relay_mode", ATTR_OPTION: "flue_fan_combustion"},
        blocking=True,
    )
    written = mock_client.set_burn_settings.call_args.args[0]
    assert written.relay_mode == 4
    assert (written.manufacturer, written.model, written.interval) == (8, 1, 480)
    assert hass.states.get("select.oven_relay_mode").state == "flue_fan_combustion"


async def test_alarm_mask_switch(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    mock_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "switch",
        DOMAIN,
        f"{DEVICE_ID}_mask_flame_sensor_error",
        suggested_object_id="oven_alarm_flame_sensor_error",
        disabled_by=None,
    )
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.oven_alarm_flame_sensor_error"},
        blocking=True,
    )
    mock_client.set_alarm_mask.assert_awaited_once_with(0x04)
    assert hass.states.get("switch.oven_alarm_flame_sensor_error").state == STATE_ON


async def test_sync_clock(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_entry)
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.oven_sync_device_clock"},
        blocking=True,
    )
    mock_client.set_clock.assert_awaited_once()


@pytest.mark.parametrize(
    ("raw", "state"),
    [(0, "idle"), (2, "heating_up"), (3, "stage_2"), (6, "stage_5"), (8, "finished"), (7, "other")],
)
async def test_phase_states(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    raw: int,
    state: str,
) -> None:
    await _setup(hass, mock_entry)
    mock_client.get_status.return_value = replace(mock_client.get_status.return_value, phase=raw)
    freezer.tick(STATUS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    phase = hass.states.get("sensor.oven_burn_phase")
    assert phase.state == state
    assert phase.attributes["raw_phase"] == raw


async def test_sync_clock_refused_during_burn(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, mock_entry)
    burning: Status = replace(mock_client.get_status.return_value, phase=4, flap=40)
    mock_client.get_status.return_value = burning
    freezer.tick(STATUS_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.oven_sync_device_clock"},
            blocking=True,
        )
    mock_client.set_clock.assert_not_awaited()


async def test_diagnostics(
    hass: HomeAssistant, mock_client: AsyncMock, mock_entry: MockConfigEntry
) -> None:
    mock_client.get_module_state.return_value = {
        **mock_client.get_module_state.return_value,
        "wifi-client-psk-key": "secret",
    }
    await _setup(hass, mock_entry)
    diag = await async_get_config_entry_diagnostics(hass, mock_entry)
    text = repr(diag)
    assert "secret" not in text
    assert "192.0.2.10" not in text
    assert diag["status"]["temperature"] == 93
    assert diag["mcu"] == {"version": 32, "build": 283}
