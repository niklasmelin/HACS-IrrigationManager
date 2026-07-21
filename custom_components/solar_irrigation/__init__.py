"""Solar Irrigation Integration."""

import logging
"""Solar Irrigation Integration."""

import logging
from datetime import datetime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SolarIrrigationCoordinator
from .progress import report_progress, update_integration_status

_LOGGER = logging.getLogger(__name__)

# Define platforms to forward
PLATFORMS = ["sensor", "switch"]

# Service handlers
async def async_run_now(hass: HomeAssistant, data):
    """Run irrigation immediately."""
    _LOGGER.debug("Running irrigation now")
    report_progress("Running irrigation now", "info")
    return True

async def async_stop_irrigation(hass: HomeAssistant, data):
    """Stop irrigation immediately."""
    _LOGGER.debug("Stopping irrigation")
    report_progress("Stopping irrigation", "info")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solar Irrigation from a config entry."""
    _LOGGER.debug("Setting up Solar Irrigation entry")
    report_progress("Starting Solar Irrigation setup", "info")
    update_integration_status("setup_starting")
    
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
    
    report_progress("Integration setup completed successfully", "success")
    update_integration_status("setup_complete")
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Solar Irrigation entry")
    report_progress("Unloading Solar Irrigation entry", "info")
    update_integration_status("unloading")
    
    # Unload platforms
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Remove data
    hass.data.pop(DOMAIN, None)
    
    report_progress("Entry unloaded successfully", "success")
    update_integration_status("unloaded")
    
    return True

async def async_setup(hass, config):
    """Set up the Solar Irrigation component."""
    report_progress("Component setup initiated", "info")
    update_integration_status("component_setup")
    return True