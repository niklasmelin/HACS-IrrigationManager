"""Typed models for the Solar Irrigation integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.config_entries import ConfigEntry

from .const import ControllerStatus

if TYPE_CHECKING:
    from .coordinator import SolarIrrigationCoordinator
    from .irrigation import SolarIrrigationController


@dataclass(frozen=True, slots=True)
class SolarIrrigationData:
    """Contain normalized inputs and calculated irrigation output."""

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

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for diagnostics and storage."""
        data = asdict(self)
        data["calculated_at"] = self.calculated_at.isoformat()
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
