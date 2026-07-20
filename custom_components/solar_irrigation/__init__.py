"""Solar Irrigation Integration."""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Irrigation from a config entry."""
    _LOGGER.debug("Setting up Solar Irrigation entry")
    
    # Store entry data for use in other components
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data
    
    # Forward the setup to the sensor and switch platforms
    await hass.async_add_executor_job(entry.data.get("setup_platforms", lambda: None))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Solar Irrigation entry")
    # Unload the entry data
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True