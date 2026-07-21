"""Constants for the Solar Irrigation integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform, UnitOfEnergy, UnitOfLength, UnitOfTime

DOMAIN: Final = "solar_irrigation"
PLATFORMS: Final[tuple[Platform, ...]] = (Platform.SENSOR,)

CONF_SOLAR_SENSOR: Final = "solar_sensor"
CONF_REMAINING_SENSOR: Final = "remaining_sensor"
CONF_IRRIGATION_ENTITY: Final = "irrigation_entity"
CONF_RAIN_SENSOR: Final = "rain_sensor"
CONF_MAX_SOLAR: Final = "max_solar"
CONF_MAX_RUNTIME: Final = "max_runtime"
CONF_RAIN_SKIP_THRESHOLD: Final = "rain_skip_threshold"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_SCHEDULE_TIME: Final = "schedule_time"
CONF_ENTRY_ID: Final = "entry_id"
CONF_DURATION: Final = "duration"
CONF_IGNORE_RAIN: Final = "ignore_rain"

DEFAULT_MAX_SOLAR: Final = 65.0
DEFAULT_MAX_RUNTIME: Final = 60.0
DEFAULT_RAIN_SKIP_THRESHOLD: Final = 5.0
DEFAULT_UPDATE_INTERVAL: Final = 3600
DEFAULT_SCHEDULE_TIME: Final = "06:00:00"

MIN_MAX_SOLAR: Final = 0.001
MAX_MAX_SOLAR: Final = 10_000.0
MIN_MAX_RUNTIME: Final = 0.0
MAX_MAX_RUNTIME: Final = 1_440.0
MIN_RAIN_SKIP_THRESHOLD: Final = 0.1
MAX_RAIN_SKIP_THRESHOLD: Final = 1_000.0
MIN_UPDATE_INTERVAL: Final = 60
MAX_UPDATE_INTERVAL: Final = 86_400

SUPPORTED_ENERGY_UNITS: Final[frozenset[str]] = frozenset(
    {
        UnitOfEnergy.WATT_HOUR,
        UnitOfEnergy.KILO_WATT_HOUR,
        UnitOfEnergy.MEGA_WATT_HOUR,
    }
)
SUPPORTED_RAIN_UNITS: Final[frozenset[str]] = frozenset(
    {
        UnitOfLength.MILLIMETERS,
        UnitOfLength.CENTIMETERS,
        UnitOfLength.INCHES,
    }
)

WH_TO_KWH: Final = 0.001
MWH_TO_KWH: Final = 1_000.0
CM_TO_MM: Final = 10.0
INCH_TO_MM: Final = 25.4
MINUTES_TO_SECONDS: Final = 60
RUNTIME_UNIT: Final = UnitOfTime.MINUTES
RUNTIME_SECONDS_UNIT: Final = UnitOfTime.SECONDS

SVC_RUN_NOW: Final = "run_now"
SVC_STOP: Final = "stop"

STORAGE_VERSION: Final = 1
STORAGE_KEY_TEMPLATE: Final = f"{DOMAIN}.{{entry_id}}"


class ControllerStatus(StrEnum):
    """Represent the current irrigation-controller status."""

    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
