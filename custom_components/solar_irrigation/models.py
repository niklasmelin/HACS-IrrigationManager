"""Typed models for Solar Irrigation integration."""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from .const import ControllerStatus

@dataclass
class SolarIrrigationData:
    """Data class for solar irrigation calculation results."""
    
    actual_solar_kwh: float
    remaining_solar_kwh: float
    expected_solar_kwh: float
    scale_factor: float
    runtime_minutes: float
    runtime_seconds: int
    calculated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "actual_solar_kwh": self.actual_solar_kwh,
            "remaining_solar_kwh": self.remaining_solar_kwh,
            "expected_solar_kwh": self.expected_solar_kwh,
            "scale_factor": self.scale_factor,
            "runtime_minutes": self.runtime_minutes,
            "runtime_seconds": self.runtime_seconds,
            "calculated_at": self.calculated_at.isoformat()
        }

@dataclass
class SolarIrrigationControllerState:
    """Data class for controller state management."""
    
    status: ControllerStatus
    last_execution: Optional[datetime]
    active_started_at: Optional[datetime]
    active_end_at: Optional[datetime]
    last_error: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "status": self.status.value,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "active_started_at": self.active_started_at.isoformat() if self.active_started_at else None,
            "active_end_at": self.active_end_at.isoformat() if self.active_end_at else None,
            "last_error": self.last_error
        }

@dataclass 
class SolarIrrigationRuntimeData:
    """Data class for runtime data associated with a config entry."""
    
    coordinator: Any  # Will be assigned from coordinator
    controller: Any  # Will be assigned from controller
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "coordinator": self.coordinator,
            "controller": self.controller
        }