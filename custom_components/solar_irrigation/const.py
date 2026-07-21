"""Constants for the Solar Irrigation integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform, UnitOfEnergy, UnitOfTime


DOMAIN: Final = "solar_irrigation"

# Platforms
PLATFORMS: Final[tuple[Platform, ...]] = (
    Platform.SENSOR,
)

# Configuration keys
CONF_SOLAR_SENSOR: Final = "solar_sensor"
CONF_REMAINING_SENSOR: Final = "remaining_sensor"
CONF_IRRIGATION_ENTITY: Final = "irrigation_entity"
CONF_MAX_SOLAR: Final = "max_solar"
CONF_MAX_RUNTIME: Final = "max_runtime"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# Default values
DEFAULT_MAX_SOLAR: Final = 65.0
DEFAULT_MAX_RUNTIME: Final = 60.0
DEFAULT_UPDATE_INTERVAL: Final = 3600

# Supported units
SUPPORTED_ENERGY_UNITS: Final[frozenset[str]] = frozenset(
    {
        UnitOfEnergy.WATT_HOUR,
        UnitOfEnergy.KILO_WATT_HOUR,
        UnitOfEnergy.MEGA_WATT_HOUR,
    }
)

RUNTIME_UNIT: Final = UnitOfTime.MINUTES
RUNTIME_SECONDS_UNIT: Final = UnitOfTime.SECONDS

# Sensor translation keys
SENSOR_EXPECTED_SOLAR: Final = "expected_solar_today"
SENSOR_SCALE_FACTOR: Final = "solar_scale_factor"
SENSOR_RUNTIME: Final = "irrigation_runtime"
SENSOR_RUNTIME_SECONDS: Final = "irrigation_runtime_seconds"
SENSOR_STATUS: Final = "irrigation_status"
SENSOR_LAST_IRRIGATION: Final = "last_irrigation"

# Services
SVC_RUN_NOW: Final = "run_now"
SVC_STOP: Final = "stop"

# Storage
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "solar_irrigation_storage"

# Validation limits
MIN_MAX_SOLAR: Final = 0.001
MAX_MAX_SOLAR: Final = 10_000.0

MIN_MAX_RUNTIME: Final = 0.0
MAX_MAX_RUNTIME: Final = 1_440.0

MIN_UPDATE_INTERVAL: Final = 60
MAX_UPDATE_INTERVAL: Final = 86_400

# Conversion factors
WH_TO_KWH: Final = 0.001
MWH_TO_KWH: Final = 1_000.0
MINUTES_TO_SECONDS: Final = 60


class ControllerStatus(StrEnum):
    """Possible irrigation-controller states."""

    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
