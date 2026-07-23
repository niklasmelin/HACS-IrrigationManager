"""Constants for the Solar Irrigation integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform, UnitOfEnergy, UnitOfLength, UnitOfTime

DOMAIN: Final = "solar_irrigation"
PLATFORMS: Final[tuple[Platform, ...]] = (Platform.SENSOR, Platform.NUMBER)

CONF_SOLAR_SENSOR: Final = "solar_sensor"
CONF_REMAINING_SENSOR: Final = "remaining_sensor"
CONF_IRRIGATION_ENTITY: Final = "irrigation_entity"
CONF_RAIN_SENSOR: Final = "rain_sensor"
CONF_MAX_SOLAR: Final = "max_solar"
CONF_PEAK_DAILY_WATER_DEMAND: Final = "max_runtime"
# Backward-compatible alias for config entries created before version 2.2.
CONF_MAX_RUNTIME: Final = CONF_PEAK_DAILY_WATER_DEMAND
CONF_RAIN_SKIP_THRESHOLD: Final = "rain_skip_threshold"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_SCHEDULE_TIME: Final = "schedule_time"  # Legacy key used before 2.3.
CONF_WATERING_WINDOW_START: Final = "watering_window_start"
CONF_WATERING_WINDOW_END: Final = "watering_window_end"
CONF_MAX_PULSE_DURATION: Final = "max_pulse_duration"
CONF_SOAK_DURATION: Final = "soak_duration"

# Legacy service field retained so existing scripts continue to work.
CONF_ENTRY_ID: Final = "entry_id"
CONF_DURATION: Final = "duration"
CONF_IGNORE_RAIN: Final = "ignore_rain"

DEFAULT_MAX_SOLAR: Final = 65.0
DEFAULT_PEAK_DAILY_WATER_DEMAND: Final = 60.0
DEFAULT_MAX_RUNTIME: Final = DEFAULT_PEAK_DAILY_WATER_DEMAND
DEFAULT_RAIN_SKIP_THRESHOLD: Final = 5.0
DEFAULT_UPDATE_INTERVAL: Final = 3600
DEFAULT_MAX_PULSE_DURATION: Final = 3.0
DEFAULT_SOAK_DURATION: Final = 15.0

# Solar history sampling. The coordinator may refresh more often, but a sample is
# stored at most every 15 minutes and history is retained for two hours.
SOLAR_SAMPLE_INTERVAL_SECONDS: Final = 15 * 60
SOLAR_SAMPLE_MIN_ELAPSED_SECONDS: Final = SOLAR_SAMPLE_INTERVAL_SECONDS
SOLAR_HISTORY_WINDOW_SECONDS: Final = 2 * 60 * 60
SOLAR_RECENT_WINDOW_SECONDS: Final = 60 * 60
SOLAR_HISTORY_STORAGE_VERSION: Final = 1
SOLAR_HISTORY_STORAGE_KEY_TEMPLATE: Final = f"{DOMAIN}.solar_history.{{entry_id}}"

DEFAULT_SCHEDULE_TIME: Final = "06:00:00"  # Legacy default used for migration.
DEFAULT_WATERING_WINDOW_START: Final = "05:00:00"
DEFAULT_WATERING_WINDOW_END: Final = "22:00:00"
AUTOMATIC_EVALUATION_INTERVAL_SECONDS: Final = 15 * 60
MIN_AUTOMATIC_EVENT_SECONDS: Final = 60
ACTUATOR_CONFIRM_TIMEOUT_SECONDS: Final = 5

MIN_MAX_SOLAR: Final = 0.001
MAX_MAX_SOLAR: Final = 10_000.0
MIN_PEAK_DAILY_WATER_DEMAND: Final = 10.0
MAX_PEAK_DAILY_WATER_DEMAND: Final = 240.0
MIN_MAX_RUNTIME: Final = MIN_PEAK_DAILY_WATER_DEMAND
MAX_MAX_RUNTIME: Final = MAX_PEAK_DAILY_WATER_DEMAND
MIN_RAIN_SKIP_THRESHOLD: Final = 0.1
MAX_RAIN_SKIP_THRESHOLD: Final = 1_000.0
MIN_UPDATE_INTERVAL: Final = 60
MAX_UPDATE_INTERVAL: Final = 86_400
MIN_MAX_PULSE_DURATION: Final = 0.5
MAX_MAX_PULSE_DURATION: Final = 15.0
MIN_SOAK_DURATION: Final = 1.0
MAX_SOAK_DURATION: Final = 30.0

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

    INITIALIZING = "initializing"
    WAITING_FOR_HISTORY = "waiting_for_history"
    SLEEPING = "sleeping"
    MONITORING = "monitoring"
    WAITING_FOR_PULSE = "waiting_for_pulse"
    SOAKING = "soaking"
    IRRIGATING = "irrigating"
    RAIN_PAUSED = "rain_paused"
    DAILY_BUDGET_REACHED = "daily_budget_reached"
    ERROR = "error"

    # Legacy aliases retained so persisted 1.x/2.1 state can be loaded safely.
    IDLE = "monitoring"
    SCHEDULED = "waiting_for_pulse"
    RUNNING = "irrigating"
    COMPLETED = "monitoring"
