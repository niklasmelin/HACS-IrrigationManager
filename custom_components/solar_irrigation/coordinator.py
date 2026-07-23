"""Data coordinator for the Solar Irrigation integration."""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
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
    SOLAR_HISTORY_STORAGE_KEY_TEMPLATE,
    SOLAR_HISTORY_STORAGE_VERSION,
    SOLAR_HISTORY_WINDOW_SECONDS,
    SOLAR_RECENT_WINDOW_SECONDS,
    SOLAR_SAMPLE_INTERVAL_SECONDS,
    SOLAR_SAMPLE_MIN_ELAPSED_SECONDS,
    WH_TO_KWH,
)
from .models import (
    SolarEnergySample,
    SolarHistoryState,
    SolarIrrigationConfigEntry,
    SolarIrrigationData,
)

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
        configured_interval = int(
            _entry_value(entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        # Refresh at least every 15 minutes so the cumulative solar-energy sensor
        # can also act as a rolling solar-radiation proxy.
        update_interval = min(configured_interval, SOLAR_SAMPLE_INTERVAL_SECONDS)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Solar Irrigation {entry.entry_id}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.solar_history = SolarHistoryState()
        self._history_loaded = False
        self._history_store: Store[dict[str, object]] = Store(
            hass,
            SOLAR_HISTORY_STORAGE_VERSION,
            SOLAR_HISTORY_STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
        )

    async def async_load_history(self) -> None:
        """Load persisted solar baseline and rolling history once."""
        if self._history_loaded:
            return
        stored = await self._history_store.async_load()
        if stored:
            self.solar_history = SolarHistoryState.from_dict(stored)
        self._prune_history(dt_util.utcnow())
        self._history_loaded = True

    async def _async_update_data(self) -> SolarIrrigationData:
        """Read current states and return a normalized calculation result."""
        await self.async_load_history()
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

        calculated_at = dt_util.utcnow()
        await self._async_sample_solar(actual, calculated_at)
        metrics = self._history_metrics(calculated_at)

        expected = actual + remaining
        solar_factor = _clamp(expected / max_solar)
        rain_factor = 1.0 if rain_mm is None else _clamp(1.0 - rain_mm / rain_threshold)
        runtime_minutes = round(solar_factor * max_runtime * rain_factor, 3)
        runtime_seconds = round(runtime_minutes * MINUTES_TO_SECONDS)
        skip_reason = _skip_reason(expected, rain_mm, rain_threshold, runtime_seconds)

        _LOGGER.debug(
            "Solar evaluation actual=%.3f kWh expected=%.3f kWh runtime=%.2f min "
            "samples=%d solar_1h=%.3f kWh solar_2h=%.3f kWh rolling=%.3f kWh/h",
            actual,
            expected,
            runtime_minutes,
            metrics["sample_count"],
            metrics["energy_last_hour"],
            metrics["energy_last_2_hours"],
            metrics["rolling_rate"],
        )

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
            calculated_at=calculated_at,
            solar_latest_delta_kwh=metrics["latest_delta"],
            solar_energy_last_hour_kwh=metrics["energy_last_hour"],
            solar_energy_last_2_hours_kwh=metrics["energy_last_2_hours"],
            solar_rate_last_hour_kwh_per_hour=metrics["rate_last_hour"],
            solar_rate_last_2_hours_kwh_per_hour=metrics["rate_last_2_hours"],
            solar_rolling_rate_kwh_per_hour=metrics["rolling_rate"],
            solar_sample_count=metrics["sample_count"],
            solar_latest_sample_at=metrics["latest_sample_at"],
        )

    async def _async_sample_solar(self, actual_kwh: float, timestamp) -> None:
        """Store a normalized cumulative-energy delta when 15 minutes elapsed."""
        history = self.solar_history
        if history.baseline_energy_kwh is None or history.baseline_at is None:
            history.baseline_energy_kwh = actual_kwh
            history.baseline_at = timestamp
            await self._history_store.async_save(history.as_dict())
            return

        elapsed_seconds = (timestamp - history.baseline_at).total_seconds()
        if elapsed_seconds < SOLAR_SAMPLE_MIN_ELAPSED_SECONDS:
            self._prune_history(timestamp)
            return

        delta_kwh = actual_kwh - history.baseline_energy_kwh
        # A daily-energy reset, source replacement, or correction establishes a
        # fresh baseline. It must never create a negative production sample.
        if delta_kwh < 0:
            _LOGGER.info("Solar cumulative sensor reset detected; clearing history")
            history.samples.clear()
            history.baseline_energy_kwh = actual_kwh
            history.baseline_at = timestamp
            await self._history_store.async_save(history.as_dict())
            return

        rate = delta_kwh / (elapsed_seconds / 3600)
        sample = SolarEnergySample(
            timestamp=timestamp,
            cumulative_energy_kwh=round(actual_kwh, 6),
            delta_energy_kwh=round(delta_kwh, 6),
            elapsed_seconds=round(elapsed_seconds, 3),
            rate_kwh_per_hour=round(rate, 6),
        )
        history.samples.append(sample)
        history.baseline_energy_kwh = actual_kwh
        history.baseline_at = timestamp
        self._prune_history(timestamp)
        await self._history_store.async_save(history.as_dict())

    def _prune_history(self, timestamp) -> None:
        """Discard samples whose end timestamp is outside the two-hour window."""
        cutoff = timestamp - timedelta(seconds=SOLAR_HISTORY_WINDOW_SECONDS)
        self.solar_history.samples = [
            sample for sample in self.solar_history.samples if sample.timestamp >= cutoff
        ]

    def _history_metrics(self, timestamp) -> dict[str, Any]:
        """Calculate observable rolling solar metrics from accepted samples."""
        self._prune_history(timestamp)
        samples = self.solar_history.samples
        hour_cutoff = timestamp - timedelta(seconds=SOLAR_RECENT_WINDOW_SECONDS)
        recent = [sample for sample in samples if sample.timestamp >= hour_cutoff]

        energy_1h = sum(sample.delta_energy_kwh for sample in recent)
        energy_2h = sum(sample.delta_energy_kwh for sample in samples)
        elapsed_1h = sum(sample.elapsed_seconds for sample in recent)
        elapsed_2h = sum(sample.elapsed_seconds for sample in samples)
        rate_1h = energy_1h / (elapsed_1h / 3600) if elapsed_1h else 0.0
        rate_2h = energy_2h / (elapsed_2h / 3600) if elapsed_2h else 0.0
        rolling_rate = 0.7 * rate_1h + 0.3 * rate_2h

        return {
            "latest_delta": round(samples[-1].delta_energy_kwh, 4) if samples else None,
            "energy_last_hour": round(energy_1h, 4),
            "energy_last_2_hours": round(energy_2h, 4),
            "rate_last_hour": round(rate_1h, 4),
            "rate_last_2_hours": round(rate_2h, 4),
            "rolling_rate": round(rolling_rate, 4),
            "sample_count": len(samples),
            "latest_sample_at": samples[-1].timestamp if samples else None,
        }

    def solar_history_as_dict(self) -> dict[str, Any]:
        """Return complete rolling solar history for diagnostics and attributes."""
        return self.solar_history.as_dict()

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
