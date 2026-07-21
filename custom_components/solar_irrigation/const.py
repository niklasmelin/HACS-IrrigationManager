"""Constants for the Solar Irrigation integration."""

from typing import Final
from homeassistant.const import UnitOfEnergy, UnitOfTime
from enum import StrEnum

DOMAIN: Final[str] = "solar_irrigation"

# Configuration
CONF_SOLAR_SENSOR: Final[str] = "solar_sensor"
CONF_REMAINING_SENSOR: Final[str] = "remaining_sensor"
CONF_IRRIGATION_ENTITY: Final[str] = "irrigation_entity"
CONF_MAX_SOLAR: Final[str] = "max_solar"
CONF_MAX_RUNTIME: Final[str] = "max_runtime"
CONF_UPDATE_INTERVAL: Final[str] = "update_interval"

# Default values
DEFAULT_MAX_SOLAR: Final[float] = 65.0
DEFAULT_MAX_RUNTIME: Final[float] = 60.0
DEFAULT_UPDATE_INTERVAL: Final[int] = 3600  # 1 hour in seconds

# Sensors
SENSOR_EXPECTED_SOLAR: Final[str] = "expected_solar_today"
SENSOR_SCALE_FACTOR: Final[str] = "solar_scale_factor"
SENSOR_RUNTIME: Final[str] = "irrigation_runtime"
SENSOR_RUNTIME_SECONDS: Final[str] = "irrigation_runtime_seconds"
SENSOR_STATUS: Final[str] = "irrigation_status"
SENSOR_LAST_IRRIGATION: Final[str] = "last_irrigation"

# Entities
ENTITY_ID_FORMAT: Final[str] = "{}_{}"

# Services
SVC_RUN_NOW: Final[str] = "run_now"
SVC_STOP: Final[str] = "stop"

# Controller status
class ControllerStatus(StrEnum):
    """Controller status enumeration."""
    
    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"

# Storage constants
STORAGE_VERSION: Final[int] = 1
STORAGE_KEY: Final[str] = "solar_irrigation_storage"

# Limits
MIN_MAX_SOLAR: Final[float] = 0.001
MAX_MAX_SOLAR: Final[float] = 10000.0
MIN_MAX_RUNTIME: Final[float] = 0.0
MAX_MAX_RUNTIME: Final[float] = 1440.0  # 24 hours