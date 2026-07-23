"""Tests for typed Solar Irrigation models."""

from datetime import UTC, datetime

from custom_components.solar_irrigation.const import ControllerStatus
from custom_components.solar_irrigation.models import (
    SolarIrrigationControllerState,
    SolarIrrigationData,
)


def test_calculation_serialization_supports_optional_rain() -> None:
    """Test that diagnostic serialization preserves an omitted rain value."""
    data = SolarIrrigationData(
        actual_solar_kwh=10,
        remaining_solar_kwh=5,
        expected_solar_kwh=15,
        solar_factor=0.5,
        rain_mm=None,
        rain_factor=1.0,
        runtime_minutes=30,
        runtime_seconds=1800,
        skip_reason=None,
        calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert data.as_dict()["rain_mm"] is None
    assert data.as_dict()["calculated_at"] == "2026-01-01T00:00:00+00:00"


def test_controller_state_round_trip() -> None:
    """Test current pulse, requested, actual, and result state round-trips."""
    state = SolarIrrigationControllerState(
        status=ControllerStatus.SOAKING,
        requested_duration_seconds=420,
        current_pulse_requested_seconds=180,
        cycle_remaining_seconds=240,
        last_duration_seconds=180,
        last_result="partial",
        next_pulse_at=datetime(2026, 1, 1, 12, 15, tzinfo=UTC),
        last_skip_reason="watering_window_closed",
    )
    restored = SolarIrrigationControllerState.from_dict(state.as_dict())
    assert restored.status is ControllerStatus.SOAKING
    assert restored.requested_duration_seconds == 420
    assert restored.current_pulse_requested_seconds == 180
    assert restored.cycle_remaining_seconds == 240
    assert restored.last_duration_seconds == 180
    assert restored.last_result == "partial"
    assert restored.next_pulse_at == datetime(2026, 1, 1, 12, 15, tzinfo=UTC)


def test_legacy_completed_status_migrates_to_monitoring() -> None:
    """Test older stored status text maps to the current controller model."""
    restored = SolarIrrigationControllerState.from_dict(
        {"status": "completed", "last_duration_seconds": 60}
    )
    assert restored.status is ControllerStatus.MONITORING
    assert restored.requested_duration_seconds == 60
    assert restored.last_duration_seconds == 60
