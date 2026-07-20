"""Solar Irrigation Integration."""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarIrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

# Define platforms to forward
PLATFORMS = ["sensor", "switch"]

# Service handlers
async def async_run_now(hass: HomeAssistant, data):
    """Run irrigation immediately."""
    _LOGGER.debug("Running irrigation now")
    # Implementation would go here
    return True

async def async_stop_irrigation(hass: HomeAssistant, data):
    """Stop irrigation immediately."""
    _LOGGER.debug("Stopping irrigation")
    # Implementation would go here
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Irrigation from a config entry."""
    _LOGGER.debug("Setting up Solar Irrigation entry")
    
    # Create and register the coordinator
    coordinator = SolarIrrigationCoordinator(hass, entry.data.get("update_interval", 3600))
    
    # Initialize the coordinator
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Forward entry to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        "run_now",
        async_run_now
    )
    
    hass.services.async_register(
        DOMAIN,
        "stop",
        async_stop_irrigation
    )
    
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