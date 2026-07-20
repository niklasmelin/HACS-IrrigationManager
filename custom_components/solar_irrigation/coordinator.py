"""Data coordinator for Solar Irrigation integration."""

import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import now

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class SolarIrrigationCoordinator(DataUpdateCoordinator):
    """Data coordinator for Solar Irrigation."""

    def __init__(self, hass: HomeAssistant, update_interval: int):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.hass = hass

    async def _async_update_data(self):
        """Fetch data from external API or sensors."""
        _LOGGER.debug("Updating Solar Irrigation data")
        
        # Get the config entry data
        entry = self.config_entry
        if not entry:
            _LOGGER.warning("No config entry found")
            return {"error": "No config entry"}
        
        # Get sensor values from the configuration
        solar_sensor = entry.data.get("solar_sensor")
        remaining_sensor = entry.data.get("remaining_sensor")
        max_solar = entry.data.get("max_solar", 65)  # Default 65 kWh
        max_runtime = entry.data.get("max_runtime", 60)  # Default 60 minutes
        update_interval = entry.data.get("update_interval", 3600)  # Default 1 hour
        
        # Read sensor values
        solar_value = self._get_sensor_value(solar_sensor)
        remaining_value = self._get_sensor_value(remaining_sensor)
        
        # Validate sensor values
        if solar_value is None or remaining_value is None:
            _LOGGER.error("Could not read sensor values")
            return {"error": "Invalid sensor values"}
        
        # Calculate expected solar energy
        expected_solar = solar_value + remaining_value
        
        # Calculate scale factor (clamp between 0 and 1)
        scale_factor = min(expected_solar / max_solar, 1.0)
        scale_factor = max(scale_factor, 0.0)  # Ensure not negative
        
        # Calculate runtime
        runtime_minutes = scale_factor * max_runtime
        
        # Convert to seconds for precision
        runtime_seconds = round(runtime_minutes * 60)
        
        # Return calculated data
        return {
            "expected_solar": expected_solar,
            "scale_factor": scale_factor,
            "runtime_minutes": runtime_minutes,
            "runtime_seconds": runtime_seconds,
            "status": "idle"
        }

    def _get_sensor_value(self, entity_id):
        """Get sensor value from HA entity."""
        if not entity_id:
            return None
            
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                _LOGGER.error(f"Could not convert sensor {entity_id} value to float: {state.state}")
        return None