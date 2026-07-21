"""Tests for Solar Irrigation integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN

from custom_components.solar_irrigation import (
    async_setup_entry,
    async_unload_entry,
    DOMAIN
)

@pytest.fixture(name="mock_entry")
def mock_config_entry():
    """Create a mock config entry."""
    return MagicMock()

@pytest.fixture(name="hass")
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock()

@pytest.mark.asyncio
async def test_async_setup_entry(hass: HomeAssistant, mock_entry: ConfigEntry):
    """Test async_setup_entry function."""
    # Mock the coordinator and platforms
    mock_coordinator = AsyncMock()
    mock_entry.data = {"update_interval": 3600}
    
    # Test successful setup
    assert await async_setup_entry(hass, mock_entry) is True

@pytest.mark.asyncio
async def test_async_unload_entry(hass: HomeAssistant, mock_entry: ConfigEntry):
    """Test async_unload_entry function."""
    # Test successful unload
    assert await async_unload_entry(hass, mock_entry) is True

def test_domain_exists():
    """Test that the domain is correctly defined."""
    assert DOMAIN == "solar_irrigation"