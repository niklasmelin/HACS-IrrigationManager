"""Core irrigation logic for Solar Irrigation integration."""

import logging
from datetime import datetime, timedelta
import math

from homeassistant.util.dt import now

_LOGGER = logging.getLogger(__name__)

class SolarIrrigationController:
    """Controller for managing irrigation based on solar energy."""

    def __init__(self, hass, config):
        """Initialize the controller."""
        self.hass = hass
        self.config = config
        self.last_execution = None
        
    def calculate_runtime(self, current_solar, remaining_solar, max_solar, max_runtime):
        """Calculate irrigation runtime based on solar energy."""
        # Calculate total solar energy for the day
        total_solar = current_solar + remaining_solar
        
        # Calculate scale factor (0.0 to 1.0)
        scale_factor = min(total_solar / max_solar, 1.0)
        
        # Calculate runtime
        runtime_minutes = scale_factor * max_runtime
        
        # Round to nearest second
        runtime_seconds = round(runtime_minutes * 60)
        
        return runtime_seconds
    
    def should_run_irrigation(self):
        """Check if irrigation should run today."""
        # Check if irrigation has already run today
        if self.last_execution:
            # Check if last execution was today
            last_executed_date = self.last_execution.date()
            today = datetime.now().date()
            
            if last_executed_date == today:
                return False
                
        return True
    
    def schedule_irrigation(self, runtime_seconds):
        """Schedule irrigation to run."""
        _LOGGER.info(f"Scheduling irrigation for {runtime_seconds} seconds")
        # Implementation would schedule the irrigation run
        return True