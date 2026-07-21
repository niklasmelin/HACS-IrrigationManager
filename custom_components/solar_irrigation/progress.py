"""Progress reporting for Solar Irrigation integration."""

import logging
from datetime import datetime
from typing import Dict, Any

_LOGGER = logging.getLogger(__name__)

class SolarIrrigationProgress:
    """Manages progress reporting for the Solar Irrigation integration."""
    
    def __init__(self):
        """Initialize progress tracker."""
        self._progress_messages = []
        self._last_update = None
        self._current_status = "initializing"
        
    def add_progress(self, message: str, level: str = "info"):
        """Add a progress message to the tracker."""
        timestamp = datetime.now().isoformat()
        progress_entry = {
            "timestamp": timestamp,
            "message": message,
            "level": level
        }
        self._progress_messages.append(progress_entry)
        _LOGGER.debug(f"[Progress] {level.upper()}: {message}")
        
    def update_status(self, status: str):
        """Update the current status."""
        self._current_status = status
        _LOGGER.debug(f"[Status] {status}")
        
    def get_progress_report(self) -> Dict[str, Any]:
        """Generate a progress report."""
        return {
            "status": self._current_status,
            "messages": self._progress_messages,
            "last_update": self._last_update,
            "total_messages": len(self._progress_messages)
        }
        
    def clear_progress(self):
        """Clear all progress messages."""
        self._progress_messages.clear()
        self._current_status = "idle"
        
    def get_current_status(self) -> str:
        """Get current status."""
        return self._current_status
        
    def get_last_message(self) -> str:
        """Get the last progress message."""
        if self._progress_messages:
            return self._progress_messages[-1]["message"]
        return "No progress messages"
        
    def get_progress_summary(self) -> str:
        """Get a summary of progress."""
        if not self._progress_messages:
            return "No progress yet"
            
        return f"Progress: {len(self._progress_messages)} messages, Last: {self._progress_messages[-1]['message']}"

# Global progress tracker instance
progress_tracker = SolarIrrigationProgress()

def report_progress(message: str, level: str = "info"):
    """Report progress for the Solar Irrigation integration."""
    progress_tracker.add_progress(message, level)

def update_integration_status(status: str):
    """Update the integration status."""
    progress_tracker.update_status(status)

def get_integration_progress():
    """Get current integration progress."""
    return progress_tracker.get_progress_report()

def get_integration_status():
    """Get current integration status."""
    return progress_tracker.get_current_status()