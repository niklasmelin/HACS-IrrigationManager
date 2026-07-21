"""Data coordinator for the Solar Irrigation integration."""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CM_TO_MM,
    CONF_MAX_RUNTIME,
    CONF_MAX_SOLAR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SKIP_THRESHOLD,
    CONF_REMAINING_SENSOR,
    CONF_SOLAR_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_MAX_SOLAR,
    DEFAULT_RAIN_SKIP_THRESHOLD,
    DEFAULT_UPDATE_INTERVAL,
    INCH_TO_MM,
    MINUTES_TO_SECONDS,
    MWH_TO_KWH,
    WH_TO_KWH,
)
from .models import SolarIrrigationConfigEntry, SolarIrrigationData

_LOGGER = logging.getLogger(__name__)


class SolarIrrigationCoordinator(DataUpdateCoordinator[SolarIrrigationData]):
    """Read source sensors and calculate irrigation requirements."""

    config_entry: SolarIrrigationConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SolarIrrigationConfigEntry,
    ) -> None:
        """Initialize the coordinator for one config entry."""
        update_interval = int(_entry_value(entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Solar Irrigation {entry.entry_id}",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> SolarIrrigationData:
        """Read current states and return a normalized calculation result."""
        try:
            actual = self._read_energy_sensor(
                str(_entry_value(self.config_entry, CONF_SOLAR_SENSOR, ""))
            )
            remaining = self._read_energy_sensor(
                str(_entry_value(self.config_entry, CONF_REMAINING_SENSOR, ""))
            )
            max_solar = float(
                _entry_value(self.config_entry, CONF_MAX_SOLAR, DEFAULT_MAX_SOLAR)
            )
            max_runtime = float(
                _entry_value(self.config_entry, CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
            )
            rain_entity = _entry_value(self.config_entry, CONF_RAIN_SENSOR, None)
            rain_mm = self._read_rain_sensor(str(rain_entity)) if rain_entity else None
            rain_threshold = float(
                _entry_value(
                    self.config_entry,
                    CONF_RAIN_SKIP_THRESHOLD,
                    DEFAULT_RAIN_SKIP_THRESHOLD,
                )
            )
        except (TypeError, ValueError) as err:
            raise UpdateFailed(str(err)) from err

        if max_solar <= 0:
            raise UpdateFailed("Maximum solar production must be greater than zero")
        if max_runtime < 0:
            raise UpdateFailed("Maximum runtime cannot be negative")
        if rain_entity and rain_threshold <= 0:
            raise UpdateFailed("Rain threshold must be greater than zero")

        expected = actual + remaining
        solar_factor = _clamp(expected / max_solar)
        rain_factor = 1.0 if rain_mm is None else _clamp(1.0 - rain_mm / rain_threshold)
        runtime_minutes = round(solar_factor * max_runtime * rain_factor, 3)
        runtime_seconds = round(runtime_minutes * MINUTES_TO_SECONDS)
        skip_reason = _skip_reason(expected, rain_mm, rain_threshold, runtime_seconds)

        return SolarIrrigationData(
            actual_solar_kwh=round(actual, 4),
            remaining_solar_kwh=round(remaining, 4),
            expected_solar_kwh=round(expected, 4),
            solar_factor=round(solar_factor, 4),
            rain_mm=None if rain_mm is None else round(rain_mm, 3),
            rain_factor=round(rain_factor, 4),
            runtime_minutes=runtime_minutes,
            runtime_seconds=runtime_seconds,
            skip_reason=skip_reason,
            calculated_at=dt_util.utcnow(),
        )

    def _read_energy_sensor(self, entity_id: str) -> float:
        """Read a finite non-negative energy state and normalize it to kWh."""
        value, unit = self._read_number_and_unit(entity_id)
        if value < 0:
            raise ValueError(f"Energy sensor {entity_id} cannot be negative")
        if unit == UnitOfEnergy.WATT_HOUR:
            return value * WH_TO_KWH
        if unit == UnitOfEnergy.KILO_WATT_HOUR:
            return value
        if unit == UnitOfEnergy.MEGA_WATT_HOUR:
            return value * MWH_TO_KWH
        raise ValueError(f"Energy sensor {entity_id} has unsupported unit {unit!r}")

    def _read_rain_sensor(self, entity_id: str) -> float:
        """Read a finite non-negative precipitation state and normalize it to mm."""
        value, unit = self._read_number_and_unit(entity_id)
        if value < 0:
            raise ValueError(f"Rain sensor {entity_id} cannot be negative")
        if unit == UnitOfLength.MILLIMETERS:
            return value
        if unit == UnitOfLength.CENTIMETERS:
            return value * CM_TO_MM
        if unit == UnitOfLength.INCHES:
            return value * INCH_TO_MM
        raise ValueError(f"Rain sensor {entity_id} has unsupported unit {unit!r}")

    def _read_number_and_unit(self, entity_id: str) -> tuple[float, str]:
        """Return a finite numeric state and its required unit of measurement."""
        if not entity_id:
            raise ValueError("A required sensor entity is not configured")
        state = self.hass.states.get(entity_id)
        if state is None:
            raise ValueError(f"Sensor {entity_id} does not exist")
        if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, ""}:
            raise ValueError(f"Sensor {entity_id} is unavailable")
        try:
            value = float(state.state)
        except (TypeError, ValueError) as err:
            raise ValueError(f"Sensor {entity_id} is not numeric") from err
        if not math.isfinite(value):
            raise ValueError(f"Sensor {entity_id} must be finite")
        unit = state.attributes.get("unit_of_measurement")
        if not isinstance(unit, str) or not unit:
            raise ValueError(f"Sensor {entity_id} has no unit of measurement")
        return value, unit


def _entry_value(entry: SolarIrrigationConfigEntry, key: str, default: Any) -> Any:
    """Read a config option, falling back to immutable entry data."""
    return entry.options.get(key, entry.data.get(key, default))


def _clamp(value: float) -> float:
    """Clamp a floating-point value to the inclusive range zero through one."""
    return max(0.0, min(value, 1.0))


def _skip_reason(
    expected_solar: float,
    rain_mm: float | None,
    rain_threshold: float,
    runtime_seconds: int,
) -> str | None:
    """Return the reason irrigation should be skipped, when applicable."""
    if rain_mm is not None and rain_mm >= rain_threshold:
        return "rain_threshold_reached"
    if expected_solar <= 0:
        return "no_solar"
    if runtime_seconds <= 0:
        return "zero_runtime"
    return None
