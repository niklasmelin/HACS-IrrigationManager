"""Data coordinator for the Solar Irrigation integration."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CM_TO_MM,
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    CONF_MAX_SOLAR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SKIP_THRESHOLD,
    CONF_REMAINING_SENSOR,
    CONF_SOAK_DURATION,
    CONF_SOLAR_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_MAX_SOLAR,
    DEFAULT_RAIN_SKIP_THRESHOLD,
    DEFAULT_SOAK_DURATION,
    DEFAULT_UPDATE_INTERVAL,
    INCH_TO_MM,
    MAX_MAX_PULSE_DURATION,
    MAX_MAX_RUNTIME,
    MAX_MAX_SOLAR,
    MAX_RAIN_SKIP_THRESHOLD,
    MAX_SOAK_DURATION,
    MAX_UPDATE_INTERVAL,
    MIN_MAX_PULSE_DURATION,
    MIN_MAX_RUNTIME,
    MIN_MAX_SOLAR,
    MIN_RAIN_SKIP_THRESHOLD,
    MIN_SOAK_DURATION,
    MIN_UPDATE_INTERVAL,
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
from .watering_window import entry_value

_LOGGER = logging.getLogger(__name__)


class SolarIrrigationCoordinator(DataUpdateCoordinator[SolarIrrigationData]):
    """Read source sensors and calculate the current daily water budget.

    The actual daily solar sensor and the remaining-production forecast are both
    normalized to kWh. Their sum estimates the complete solar production for the
    current day. This estimate is divided by the configured peak daily solar
    production and multiplied by peak daily water demand and the optional rain
    factor. The result is a daily pump-runtime budget, not one uninterrupted run.
    """

    config_entry: SolarIrrigationConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SolarIrrigationConfigEntry,
    ) -> None:
        """Initialize the coordinator and entry-specific solar-history storage."""
        try:
            configured_interval = int(
                entry_value(entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            )
        except (TypeError, ValueError):
            configured_interval = DEFAULT_UPDATE_INTERVAL
        # Refresh at least every 15 minutes so the cumulative solar sensor also
        # supplies a rolling two-hour solar-radiation proxy. The minimum prevents
        # a malformed legacy entry from creating a tight refresh loop before
        # normal runtime validation reports the configuration error.
        update_interval = min(
            max(configured_interval, MIN_UPDATE_INTERVAL),
            SOLAR_SAMPLE_INTERVAL_SECONDS,
        )
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

    async def async_calculate_dry_budget_seconds(self) -> int:
        """Return a fresh solar-scaled budget without reading optional rain.

        Manual ``run_now`` calls with Ignore rain enabled still need current solar
        production and the remaining-production forecast when no explicit
        duration is supplied. Reading those inputs separately keeps that operator
        override usable even when a configured rain sensor is unavailable.
        The actual cumulative value is also sampled so manual operation does not
        create a gap in the rolling solar history.
        """
        await self.async_load_history()
        try:
            actual = self._read_energy_sensor(
                str(entry_value(self.config_entry, CONF_SOLAR_SENSOR, ""))
            )
            remaining = self._read_energy_sensor(
                str(entry_value(self.config_entry, CONF_REMAINING_SENSOR, ""))
            )
            max_solar = float(
                entry_value(self.config_entry, CONF_MAX_SOLAR, DEFAULT_MAX_SOLAR)
            )
            max_runtime = float(
                entry_value(self.config_entry, CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
            )
        except (TypeError, ValueError) as err:
            raise UpdateFailed(str(err)) from err

        _validate_range(
            max_solar,
            MIN_MAX_SOLAR,
            MAX_MAX_SOLAR,
            "Peak daily solar production",
        )
        _validate_range(
            max_runtime,
            MIN_MAX_RUNTIME,
            MAX_MAX_RUNTIME,
            "Peak daily water demand",
        )
        calculated_at = dt_util.utcnow()
        await self._async_sample_solar(actual, calculated_at)
        solar_factor = _clamp((actual + remaining) / max_solar)
        return round(solar_factor * max_runtime * MINUTES_TO_SECONDS)

    async def _async_update_data(self) -> SolarIrrigationData:
        """Read current states and return a normalized calculation result."""
        await self.async_load_history()
        try:
            actual = self._read_energy_sensor(
                str(entry_value(self.config_entry, CONF_SOLAR_SENSOR, ""))
            )
            remaining = self._read_energy_sensor(
                str(entry_value(self.config_entry, CONF_REMAINING_SENSOR, ""))
            )
            max_solar = float(
                entry_value(self.config_entry, CONF_MAX_SOLAR, DEFAULT_MAX_SOLAR)
            )
            max_runtime = float(
                entry_value(self.config_entry, CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
            )
            rain_entity = entry_value(self.config_entry, CONF_RAIN_SENSOR, None)
            rain_mm = self._read_rain_sensor(str(rain_entity)) if rain_entity else None
            rain_threshold = float(
                entry_value(
                    self.config_entry,
                    CONF_RAIN_SKIP_THRESHOLD,
                    DEFAULT_RAIN_SKIP_THRESHOLD,
                )
            )
            update_interval = float(
                entry_value(
                    self.config_entry,
                    CONF_UPDATE_INTERVAL,
                    DEFAULT_UPDATE_INTERVAL,
                )
            )
            max_pulse_duration = float(
                entry_value(
                    self.config_entry,
                    CONF_MAX_PULSE_DURATION,
                    DEFAULT_MAX_PULSE_DURATION,
                )
            )
            soak_duration = float(
                entry_value(
                    self.config_entry,
                    CONF_SOAK_DURATION,
                    DEFAULT_SOAK_DURATION,
                )
            )
        except (TypeError, ValueError) as err:
            raise UpdateFailed(str(err)) from err

        _validate_range(
            max_solar,
            MIN_MAX_SOLAR,
            MAX_MAX_SOLAR,
            "Peak daily solar production",
        )
        _validate_range(
            max_runtime,
            MIN_MAX_RUNTIME,
            MAX_MAX_RUNTIME,
            "Peak daily water demand",
        )
        _validate_range(
            update_interval,
            MIN_UPDATE_INTERVAL,
            MAX_UPDATE_INTERVAL,
            "Calculation update interval",
        )
        _validate_range(
            max_pulse_duration,
            MIN_MAX_PULSE_DURATION,
            MAX_MAX_PULSE_DURATION,
            "Maximum pulse duration",
        )
        _validate_range(
            soak_duration,
            MIN_SOAK_DURATION,
            MAX_SOAK_DURATION,
            "Soak duration",
        )
        if rain_entity:
            _validate_range(
                rain_threshold,
                MIN_RAIN_SKIP_THRESHOLD,
                MAX_RAIN_SKIP_THRESHOLD,
                "Rain skip threshold",
            )

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
            "Solar evaluation actual=%.3f kWh remaining=%.3f kWh "
            "expected=%.3f kWh budget=%.2f min samples=%d solar_1h=%.3f kWh "
            "solar_2h=%.3f kWh rolling=%.3f kWh/h",
            actual,
            remaining,
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

    async def _async_sample_solar(
        self,
        actual_kwh: float,
        timestamp: datetime,
    ) -> None:
        """Store a cumulative-energy delta after a useful sampling interval.

        Delayed samples remain valid. Their full accumulated energy is retained,
        and rolling-window calculations later include only the proportional part
        overlapping the one-hour or two-hour window. This preserves information
        without treating several missed intervals as one instantaneous spike.
        """
        history = self.solar_history
        if history.baseline_energy_kwh is None or history.baseline_at is None:
            await self._async_rebaseline_from_local_midnight(actual_kwh, timestamp)
            return

        baseline_local_date = dt_util.as_local(history.baseline_at).date()
        sample_local_date = dt_util.as_local(timestamp).date()
        if baseline_local_date != sample_local_date:
            _LOGGER.info("New local solar day detected; rebuilding history baseline")
            await self._async_rebaseline_from_local_midnight(actual_kwh, timestamp)
            return

        elapsed_seconds = (timestamp - history.baseline_at).total_seconds()
        if elapsed_seconds < SOLAR_SAMPLE_MIN_ELAPSED_SECONDS:
            self._prune_history(timestamp)
            return

        delta_kwh = actual_kwh - history.baseline_energy_kwh
        # A normal daily reset or source correction establishes a new baseline.
        # A negative production sample must never be exposed to the algorithm.
        if delta_kwh < 0:
            _LOGGER.info("Solar cumulative sensor reset detected; rebuilding baseline")
            await self._async_rebaseline_from_local_midnight(actual_kwh, timestamp)
            return

        rate = delta_kwh / (elapsed_seconds / 3600)
        history.samples.append(
            SolarEnergySample(
                timestamp=timestamp,
                cumulative_energy_kwh=round(actual_kwh, 6),
                delta_energy_kwh=round(delta_kwh, 6),
                elapsed_seconds=round(elapsed_seconds, 3),
                rate_kwh_per_hour=round(rate, 6),
            )
        )
        history.baseline_energy_kwh = actual_kwh
        history.baseline_at = timestamp
        self._prune_history(timestamp)
        await self._history_store.async_save(history.as_dict())

    async def _async_rebaseline_from_local_midnight(
        self,
        actual_kwh: float,
        timestamp: datetime,
    ) -> None:
        """Rebuild history from the cumulative value measured since midnight.

        The daily source value remains meaningful after a restart or missed samples.
        Representing it as one interval from local midnight preserves the exact total
        energy while the overlap calculation spreads only a proportional share into
        the latest one-hour and two-hour windows. Later 15-minute samples naturally
        replace this coarse estimate as the rolling window advances.
        """
        history = self.solar_history
        history.samples.clear()
        local_timestamp = dt_util.as_local(timestamp)
        local_midnight = local_timestamp.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        interval_start = local_midnight.astimezone(timestamp.tzinfo)
        elapsed_seconds = max(0.0, (timestamp - interval_start).total_seconds())
        if elapsed_seconds >= SOLAR_SAMPLE_MIN_ELAPSED_SECONDS:
            rate = actual_kwh / (elapsed_seconds / 3600)
            history.samples.append(
                SolarEnergySample(
                    timestamp=timestamp,
                    cumulative_energy_kwh=round(actual_kwh, 6),
                    delta_energy_kwh=round(actual_kwh, 6),
                    elapsed_seconds=round(elapsed_seconds, 3),
                    rate_kwh_per_hour=round(rate, 6),
                )
            )
        history.baseline_energy_kwh = actual_kwh
        history.baseline_at = timestamp
        self._prune_history(timestamp)
        await self._history_store.async_save(history.as_dict())

    def _prune_history(self, timestamp: datetime) -> None:
        """Discard samples whose end timestamp is outside the two-hour window."""
        cutoff = timestamp - timedelta(seconds=SOLAR_HISTORY_WINDOW_SECONDS)
        self.solar_history.samples = [
            sample for sample in self.solar_history.samples if sample.timestamp >= cutoff
        ]

    def _history_metrics(self, timestamp: datetime) -> dict[str, Any]:
        """Calculate observable rolling metrics using interval overlap.

        A delayed sample can represent more than 15 minutes. Only the fraction of
        its energy and elapsed time that overlaps the requested window is counted.
        This balanced treatment avoids both discarding useful accumulated energy
        and falsely assigning a multi-hour delta entirely to the latest hour.
        """
        self._prune_history(timestamp)
        samples = self.solar_history.samples
        hour_cutoff = timestamp - timedelta(seconds=SOLAR_RECENT_WINDOW_SECONDS)
        two_hour_cutoff = timestamp - timedelta(seconds=SOLAR_HISTORY_WINDOW_SECONDS)

        energy_1h, elapsed_1h = _window_totals(samples, hour_cutoff, timestamp)
        energy_2h, elapsed_2h = _window_totals(samples, two_hour_cutoff, timestamp)
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


def _window_totals(
    samples: list[SolarEnergySample],
    cutoff: datetime,
    timestamp: datetime,
) -> tuple[float, float]:
    """Return energy and elapsed seconds overlapping a rolling time window."""
    energy = 0.0
    elapsed = 0.0
    for sample in samples:
        if sample.elapsed_seconds <= 0:
            continue
        sample_start = sample.timestamp - timedelta(seconds=sample.elapsed_seconds)
        overlap_start = max(sample_start, cutoff)
        overlap_end = min(sample.timestamp, timestamp)
        overlap_seconds = (overlap_end - overlap_start).total_seconds()
        if overlap_seconds <= 0:
            continue
        fraction = min(1.0, overlap_seconds / sample.elapsed_seconds)
        energy += sample.delta_energy_kwh * fraction
        elapsed += overlap_seconds
    return energy, elapsed


def _validate_range(value: float, minimum: float, maximum: float, label: str) -> None:
    """Raise ``UpdateFailed`` when a configured numeric value is out of range."""
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise UpdateFailed(f"{label} must be between {minimum:g} and {maximum:g}")


def _clamp(value: float) -> float:
    """Clamp a floating-point value to the inclusive range zero through one."""
    return max(0.0, min(value, 1.0))


def _skip_reason(
    expected_solar: float,
    rain_mm: float | None,
    rain_threshold: float,
    runtime_seconds: int,
) -> str | None:
    """Return the reason the current daily budget is zero, when applicable."""
    if rain_mm is not None and rain_mm >= rain_threshold:
        return "rain_threshold_reached"
    if expected_solar <= 0:
        return "no_solar"
    if runtime_seconds <= 0:
        return "zero_runtime"
    return None
