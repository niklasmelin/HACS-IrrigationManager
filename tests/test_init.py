"""Tests for Solar Irrigation setup, unloading, and runtime ownership."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import PLATFORMS


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that setup stores typed runtime objects on the config entry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator is not None
    assert mock_config_entry.runtime_data.controller is not None


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that unloading one entry releases its platforms cleanly."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_forwards_exact_platforms(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that setup forwards only the declared platform tuple."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.solar_irrigation.SolarIrrigationCoordinator."
            "async_config_entry_first_refresh",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward_mock,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    forward_mock.assert_awaited_once_with(mock_config_entry, PLATFORMS)
