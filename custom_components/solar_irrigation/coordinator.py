"""Data coordinator for Solar Irrigation integration."""

import logging
from datetime import timedelta
from typing import Dict, Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import now

from .const import DOMAIN, DEFAULT_MAX_SOLAR, DEFAULT_MAX_RUNTIME
from .models import SolarIrrigationData
from .progress import report_progress, update_integration_status

_LOGGER = logging.getLogger(__name__)

class SolarIrrigationCoordinator(DataUpdateCoordinator):
    """Data coordinator for Solar Irrigation."""

    def __init__(self, hass: HomeAssistant, update_interval: int, entry_id: str):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.hass = hass
        self.entry_id = entry_id
        report_progress("Coordinator initialized", "info")
        update_integration_status("coordinator_ready")

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from external API or sensors."""
        _LOGGER.debug("Updating Solar Irrigation data")
        report_progress("Starting data update cycle", "info")
        update_integration_status("updating_data")
        
        # Get the config entry data
        entry = self.config_entry
        if not entry:
            _LOGGER.warning("No config entry found")
            report_progress("No config entry found", "warning")
            raise UpdateFailed("No config entry")
        
        # Get sensor values from the configuration
        solar_sensor = entry.data.get("solar_sensor")
        remaining_sensor = entry.data.get("remaining_sensor")
        max_solar = entry.data.get("max_solar", DEFAULT_MAX_SOLAR)  # Default 65 kWh
        max_runtime = entry.data.get("max_runtime", DEFAULT_MAX_RUNTIME)  # Default 60 minutes
        update_interval = entry.data.get("update_interval", 3600)  # Default 1 hour
        
        # Validate max solar value
        if max_solar <= 0:
            _LOGGER.error("Max solar value must be greater than zero")
            report_progress("Invalid max solar value", "error")
            raise UpdateFailed("Invalid max solar value")
        
        # Read sensor values
        solar_value = self._get_sensor_value(solar_sensor)
        remaining_value = self._get_sensor_value(remaining_sensor)
        report_progress("Retrieved sensor values", "info")
        
        # Validate sensor values
        if solar_value is None or remaining_value is None:
            _LOGGER.error("Could not read sensor values")
            report_progress("Invalid sensor values", "error")
            raise UpdateFailed("Invalid sensor values")
        
        # Validate that values are not negative
        if solar_value < 0 or remaining_value < 0:
            _LOGGER.error("Sensor values cannot be negative")
            report_progress("Negative sensor values detected", "error")
            raise UpdateFailed("Invalid sensor values: negative values detected")
        
        # Calculate expected solar energy
        expected_solar = solar_value + remaining_value
        report_progress("Calculated expected solar energy", "info")
        
        # Calculate scale factor (clamp between 0 and 1)
        scale_factor = min(expected_solar / max_solar, 1.0)
        scale_factor = max(scale_factor, 0.0)  # Ensure not negative
        report_progress("Calculated scale factor", "info")
        
        # Calculate runtime
        runtime_minutes = scale_factor * max_runtime
        report_progress("Calculated runtime", "info")
        
        # Convert to seconds for precision
        runtime_seconds = round(runtime_minutes * 60)
        report_progress("Converted runtime to seconds", "info")
        
        # Return calculated data as a proper data class
        result = SolarIrrigationData(
            actual_solar_kwh=solar_value,
            remaining_solar_kwh=remaining_value,
            expected_solar_kwh=expected_solar,
            scale_factor=scale_factor,
            runtime_minutes=runtime_minutes,
            runtime_seconds=runtime_seconds,
            calculated_at=now()
        ).to_dict()
        
        report_progress("Data update completed successfully", "success")
        update_integration_status("data_updated")
        return result

    def _get_sensor_value(self, entity_id: str) -> float:
        """Get sensor value from HA entity."""
        if not entity_id:
            return None
            
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                _LOGGER.error(f"Could not convert sensor {entity_id} value to float: {state.state}")
                report_progress(f"Failed to convert sensor {entity_id} value", "error")
        return None