"""Solar Irrigation sensors."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_EXPECTED_SOLAR,
    SENSOR_SCALE_FACTOR,
    SENSOR_RUNTIME,
    SENSOR_RUNTIME_SECONDS,
    SENSOR_STATUS,
    SENSOR_LAST_IRRIGATION,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: dict[str, Any]) -> bool:
    """Set up Solar Irrigation sensors from config entry."""
    # This function would be called to set up sensors
    return True

class SolarIrrigationSensor(CoordinatorEntity):
    """Base class for Solar Irrigation sensors."""

    def __init__(self, coordinator, unique_id, name):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._unique_id = unique_id
        self._name = name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self.coordinator.data.get("state", "unknown")

class ExpectedSolarSensor(SolarIrrigationSensor):
    """Sensor for expected solar energy."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, "expected_solar_today", "Expected Solar Today")

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "kWh"

class ScaleFactorSensor(SolarIrrigationSensor):
    """Sensor for scale factor."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, "solar_scale_factor", "Solar Scale Factor")

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return ""

class RuntimeSensor(SolarIrrigationSensor):
    """Sensor for irrigation runtime."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, "irrigation_runtime", "Irrigation Runtime")

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "min"

class RuntimeSecondsSensor(SolarIrrigationSensor):
    """Sensor for irrigation runtime in seconds."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, "irrigation_runtime_seconds", "Irrigation Runtime Seconds")

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "s"

class StatusSensor(SolarIrrigationSensor):
    """Sensor for irrigation status."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator, "irrigation_status", "Irrigation Status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "status": self.coordinator.data.get("status", "unknown")
        }