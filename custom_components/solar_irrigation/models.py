"""Typed models for the Solar Irrigation integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.config_entries import ConfigEntry

from .const import ControllerStatus

if TYPE_CHECKING:
    from .coordinator import SolarIrrigationCoordinator
    from .irrigation import SolarIrrigationController


@dataclass(frozen=True, slots=True)
class SolarEnergySample:
    """Represent one accepted cumulative-energy delta sample."""

    timestamp: datetime
    cumulative_energy_kwh: float
    delta_energy_kwh: float
    elapsed_seconds: float
    rate_kwh_per_hour: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly sample representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "cumulative_energy_kwh": self.cumulative_energy_kwh,
            "delta_energy_kwh": self.delta_energy_kwh,
            "elapsed_seconds": self.elapsed_seconds,
            "rate_kwh_per_hour": self.rate_kwh_per_hour,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolarEnergySample:
        """Restore a sample from persistent storage."""
        return cls(
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            cumulative_energy_kwh=float(data["cumulative_energy_kwh"]),
            delta_energy_kwh=float(data["delta_energy_kwh"]),
            elapsed_seconds=float(data["elapsed_seconds"]),
            rate_kwh_per_hour=float(data["rate_kwh_per_hour"]),
        )


@dataclass(slots=True)
class SolarHistoryState:
    """Hold the persisted baseline and rolling solar-energy samples."""

    baseline_energy_kwh: float | None = None
    baseline_at: datetime | None = None
    samples: list[SolarEnergySample] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly history representation."""
        return {
            "baseline_energy_kwh": self.baseline_energy_kwh,
            "baseline_at": _isoformat(self.baseline_at),
            "samples": [sample.as_dict() for sample in self.samples],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolarHistoryState:
        """Restore solar history while ignoring malformed sample records."""
        samples: list[SolarEnergySample] = []
        for raw in data.get("samples", []):
            try:
                samples.append(SolarEnergySample.from_dict(raw))
            except (KeyError, TypeError, ValueError):
                continue
        baseline = data.get("baseline_energy_kwh")
        return cls(
            baseline_energy_kwh=None if baseline is None else float(baseline),
            baseline_at=_parse_datetime(data.get("baseline_at")),
            samples=samples,
        )


@dataclass(frozen=True, slots=True)
class SolarIrrigationData:
    """Contain normalized inputs, solar history, and irrigation output."""

    actual_solar_kwh: float
    remaining_solar_kwh: float
    expected_solar_kwh: float
    solar_factor: float
    rain_mm: float | None
    rain_factor: float
    runtime_minutes: float
    runtime_seconds: int
    skip_reason: str | None
    calculated_at: datetime
    solar_latest_delta_kwh: float | None = None
    solar_energy_last_hour_kwh: float = 0.0
    solar_energy_last_2_hours_kwh: float = 0.0
    solar_rate_last_hour_kwh_per_hour: float = 0.0
    solar_rate_last_2_hours_kwh_per_hour: float = 0.0
    solar_rolling_rate_kwh_per_hour: float = 0.0
    solar_sample_count: int = 0
    solar_latest_sample_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for diagnostics and storage."""
        data = asdict(self)
        data["calculated_at"] = self.calculated_at.isoformat()
        data["solar_latest_sample_at"] = _isoformat(self.solar_latest_sample_at)
        return data


@dataclass(slots=True)
class SolarIrrigationControllerState:
    """Track persistent and observable controller state."""

    status: ControllerStatus = ControllerStatus.IDLE
    last_execution: datetime | None = None
    active_started_at: datetime | None = None
    active_end_at: datetime | None = None
    last_duration_seconds: int = 0
    last_skip_reason: str | None = None
    last_error: str | None = None
    last_automatic_date: str | None = None
    delivery_date: str | None = None
    delivered_today_seconds: int = 0
    pulse_count_today: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for storage and diagnostics."""
        return {
            "status": self.status.value,
            "last_execution": _isoformat(self.last_execution),
            "active_started_at": _isoformat(self.active_started_at),
            "active_end_at": _isoformat(self.active_end_at),
            "last_duration_seconds": self.last_duration_seconds,
            "last_skip_reason": self.last_skip_reason,
            "last_error": self.last_error,
            "last_automatic_date": self.last_automatic_date,
            "delivery_date": self.delivery_date,
            "delivered_today_seconds": self.delivered_today_seconds,
            "pulse_count_today": self.pulse_count_today,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SolarIrrigationControllerState:
        """Create controller state from persisted storage data."""
        return cls(
            status=ControllerStatus(data.get("status", ControllerStatus.IDLE)),
            last_execution=_parse_datetime(data.get("last_execution")),
            active_started_at=_parse_datetime(data.get("active_started_at")),
            active_end_at=_parse_datetime(data.get("active_end_at")),
            last_duration_seconds=int(data.get("last_duration_seconds", 0)),
            last_skip_reason=data.get("last_skip_reason"),
            last_error=data.get("last_error"),
            last_automatic_date=data.get("last_automatic_date"),
            delivery_date=data.get("delivery_date"),
            delivered_today_seconds=int(data.get("delivered_today_seconds", 0)),
            pulse_count_today=int(data.get("pulse_count_today", 0)),
        )


@dataclass(slots=True)
class SolarIrrigationRuntimeData:
    """Own all runtime objects associated with one config entry."""

    coordinator: SolarIrrigationCoordinator
    controller: SolarIrrigationController
    cancel_schedule: Callable[[], None] | None = None
    remove_update_listener: Callable[[], None] | None = None


SolarIrrigationConfigEntry = ConfigEntry[SolarIrrigationRuntimeData]


def _isoformat(value: datetime | None) -> str | None:
    """Convert an optional datetime to ISO format."""
    return value.isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an optional ISO-formatted datetime value."""
    return datetime.fromisoformat(value) if value else None
