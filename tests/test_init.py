"""Tests for Solar Irrigation integration setup and unloading."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import DOMAIN


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test successful config-entry setup."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.solar_irrigation."
        "SolarIrrigationCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        setup_result = await hass.config_entries.async_setup(
            mock_config_entry.entry_id
        )
        await hass.async_block_till_done()

    assert setup_result is True
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test successful config-entry unloading."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.solar_irrigation."
        "SolarIrrigationCoordinator.async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(
            mock_config_entry.entry_id
        )
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    unload_result = await hass.config_entries.async_unload(
        mock_config_entry.entry_id
    )
    await hass.async_block_till_done()

    assert unload_result is True
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_forwards_platforms(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that setup forwards the entry to its entity platforms."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.solar_irrigation."
            "SolarIrrigationCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward_mock,
    ):
        assert await hass.config_entries.async_setup(
            mock_config_entry.entry_id
        )
        await hass.async_block_till_done()

    forward_mock.assert_awaited_once()

    entry, platforms = forward_mock.await_args.args

    assert entry is mock_config_entry
    assert platforms