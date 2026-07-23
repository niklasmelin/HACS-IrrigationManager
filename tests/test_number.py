"""Tests for the writable Peak daily water demand entity."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import CONF_MAX_RUNTIME
from custom_components.solar_irrigation.number import PeakDailyWaterDemandNumber


async def test_peak_demand_updates_in_place_without_reload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test seasonal demand persists and refreshes without stopping an event."""
    mock_config_entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    mock_config_entry.runtime_data = SimpleNamespace(
        coordinator=coordinator,
        suppress_next_reload=False,
    )
    entity = PeakDailyWaterDemandNumber(mock_config_entry)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_native_value(90)

    assert mock_config_entry.options[CONF_MAX_RUNTIME] == 90
    assert mock_config_entry.runtime_data.suppress_next_reload is True
    coordinator.async_request_refresh.assert_awaited_once()
    entity.async_write_ha_state.assert_called_once()


async def test_peak_demand_direct_calls_are_clamped(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test internal callers cannot persist outside the 10-240 minute range."""
    mock_config_entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    mock_config_entry.runtime_data = SimpleNamespace(
        coordinator=coordinator,
        suppress_next_reload=False,
    )
    entity = PeakDailyWaterDemandNumber(mock_config_entry)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()

    await entity.async_set_native_value(500)

    assert entity.native_value == 240
