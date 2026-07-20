"""Constants for the Solar Irrigation integration."""

from homeassistant.const import (
    UnitOfEnergy,
    UnitOfTime,
)

DOMAIN = "solar_irrigation"

# Configuration
CONF_SOLAR_SENSOR = "solar_sensor"
CONF_REMAINING_SENSOR = "remaining_sensor"
CONF_IRrigation_ENTITY = "irrigation_entity"
CONF_MAX_SOLAR = "max_solar"
CONF_MAX_RUNTIME = "max_runtime"
CONF_UPDATE_INTERVAL = "update_interval"

# Default values
DEFAULT_MAX_SOLAR = 65
DEFAULT_MAX_RUNTIME = 60
DEFAULT_UPDATE_INTERVAL = 3600  # 1 hour in seconds

# Sensors
SENSOR_EXPECTED_SOLAR = "expected_solar_today"
SENSOR_SCALE_FACTOR = "solar_scale_factor"
SENSOR_RUNTIME = "irrigation_runtime"
SENSOR_RUNTIME_SECONDS = "irrigation_runtime_seconds"
SENSOR_STATUS = "irrigation_status"
SENSOR_LAST_IRRIGATION = "last_irrigation"

# Entities
ENTITY_ID_FORMAT = "{}_{}"

# Services
SVC_RUN_NOW = "run_now"
SVC_STOP = "stop"