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
    """Test that persisted controller state can be restored without data loss."""
    state = SolarIrrigationControllerState(
        status=ControllerStatus.COMPLETED,
        last_duration_seconds=60,
        last_skip_reason="rain_threshold_reached",
    )
    restored = SolarIrrigationControllerState.from_dict(state.as_dict())
    assert restored.status is ControllerStatus.COMPLETED
    assert restored.last_duration_seconds == 60
    assert restored.last_skip_reason == "rain_threshold_reached"
