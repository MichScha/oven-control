"""Fixtures for Oven Control tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_HOST

from custom_components.oven_control.api import (
    BurnParams,
    BurnSettings,
    DeviceClock,
    McuInfo,
    Status,
    WaterSettings,
    decode_alarm_log,
    decode_frame,
)
from custom_components.oven_control.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from . import frames

DEVICE_ID = frames.MODULE_STATE["device-id"]
HOST = "192.0.2.10"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
def water() -> bool:
    """Whether the mocked controller is the water variant."""
    return False


@pytest.fixture
def mock_client(water: bool) -> Generator[AsyncMock]:
    """Mock the protocol client in setup and config flow."""
    with (
        patch("custom_components.oven_control.OvenClient", autospec=True) as cls,
        patch("custom_components.oven_control.config_flow.OvenClient", new=cls),
    ):
        client = cls.return_value
        status_frame = frames.water_status() if water else frames.STATUS
        client.get_status.return_value = Status.from_frame(decode_frame(status_frame))
        client.get_module_state.return_value = dict(frames.MODULE_STATE)
        client.get_mcu_info.return_value = McuInfo.from_frame(decode_frame(frames.MCU_INFO))
        burn_params = BurnParams.from_frame(decode_frame(frames.BURN_PARAMS))
        client.get_burn_params.return_value = burn_params
        client.set_burn_params.side_effect = lambda p: p
        client.get_burn_settings.return_value = BurnSettings.from_frame(
            decode_frame(frames.BURN_SETTINGS)
        )
        client.set_burn_settings.side_effect = lambda s: s
        client.get_water_settings.return_value = WaterSettings.from_frame(
            decode_frame(frames.WATER_SETTINGS)
        )
        client.set_water_settings.side_effect = lambda s: s
        client.get_alarm_mask.return_value = 0
        client.get_clock.return_value = DeviceClock.from_frame(decode_frame(frames.CLOCK))
        client.get_alarm_log.return_value = decode_alarm_log(decode_frame(frames.ALARM_LOG))
        yield client


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """Return a config entry for the mocked controller."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=DEVICE_ID, data={CONF_HOST: HOST}, title="Oven"
    )
