"""Solar Irrigation Integration."""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define platforms to forward
PLATFORMS = ["sensor", "switch"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Irrigation from a config entry."""
    _LOGGER.debug("Setting up Solar Irrigation entry")
    
    # Create and register the coordinator
    # This is a placeholder - actual coordinator instantiation would happen here
    # coordinator = SolarIrrigationCoordinator(hass, entry.data.get("update_interval", 3600))
    # await coordinator.async_config_entry_first_refresh()
    
    # Forward entry to platforms
    hass.data.setdefault(DOMAIN, {})
    # hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Forward to sensor and switch platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Solar Irrigation entry")
    
    # Unload platforms
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Remove data
    hass.data.pop(DOMAIN, None)
    
    return True

async def async_setup(hass, config):
    """Set up the Solar Irrigation component."""
    return True