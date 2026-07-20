"""Irrigation controller for Solar Irrigation integration."""

import logging
from datetime import datetime, timedelta
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Storage
from homeassistant.util.dt import now

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class SolarIrrigationController:
    """Controller for managing irrigation operations."""

    def __init__(self, hass: HomeAssistant, coordinator):
        """Initialize the controller."""
        self.hass = hass
        self.coordinator = coordinator
        self.storage_key = f"{DOMAIN}_storage"
        
    async def async_run_irrigation(self, entity_id, duration=None):
        """Run irrigation for the specified duration."""
        _LOGGER.info(f"Starting irrigation for {entity_id}")
        
        # Get current runtime from coordinator
        if not self.coordinator.data or "runtime_seconds" not in self.coordinator.data:
            _LOGGER.error("Cannot determine runtime for irrigation")
            return False
            
        # If duration is provided, use that instead of calculated value
        if duration:
            runtime_seconds = duration * 60  # Convert minutes to seconds
        else:
            runtime_seconds = self.coordinator.data["runtime_seconds"]
            
        # Turn on the irrigation switch
        await self._turn_on_switch(entity_id)
        
        # Wait for the runtime duration
        await asyncio.sleep(runtime_seconds)
        
        # Turn off the irrigation switch
        await self._turn_off_switch(entity_id)
        
        # Record the last execution
        await self._record_execution()
        
        _LOGGER.info(f"Irrigation completed for {entity_id} for {runtime_seconds} seconds")
        return True
        
    async def _turn_on_switch(self, entity_id):
        """Turn on the irrigation switch."""
        _LOGGER.debug(f"Turning on irrigation switch: {entity_id}")
        service_data = {"entity_id": entity_id}
        await self.hass.services.async_call("switch", "turn_on", service_data)
        
    async def _turn_off_switch(self, entity_id):
        """Turn off the irrigation switch."""
        _LOGGER.debug(f"Turning off irrigation switch: {entity_id}")
        service_data = {"entity_id": entity_id}
        await self.hass.services.async_call("switch", "turn_off", service_data)
        
    async def _record_execution(self):
        """Record the last execution time."""
        # This would typically save to storage
        _LOGGER.debug("Recording execution time")
        
    async def async_stop_irrigation(self, entity_id):
        """Stop irrigation immediately."""
        _LOGGER.info(f"Stopping irrigation for {entity_id}")
        await self._turn_off_switch(entity_id)