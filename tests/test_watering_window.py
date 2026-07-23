"""Tests for daytime and overnight watering-window helpers."""

from __future__ import annotations

from datetime import UTC, datetime, time

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import (
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DOMAIN,
)
from custom_components.solar_irrigation.watering_window import (
    delivery_progress,
    is_within_watering_window,
    watering_window_bounds,
)


def _entry(start: str, end: str) -> MockConfigEntry:
    """Return a minimal config entry with one watering window."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Window",
        data={
            CONF_WATERING_WINDOW_START: start,
            CONF_WATERING_WINDOW_END: end,
        },
    )


def test_normal_window_is_start_inclusive_and_end_exclusive() -> None:
    """Test ordinary same-day window membership."""
    entry = _entry("05:00:00", "22:00:00")
    assert is_within_watering_window(entry, time(5, 0))
    assert is_within_watering_window(entry, time(12, 0))
    assert not is_within_watering_window(entry, time(22, 0))
    assert not is_within_watering_window(entry, time(4, 59))


def test_overnight_window_wraps_across_midnight() -> None:
    """Test a deliberately configured overnight watering window."""
    entry = _entry("22:00:00", "05:00:00")
    assert is_within_watering_window(entry, time(23, 0))
    assert is_within_watering_window(entry, time(4, 0))
    assert not is_within_watering_window(entry, time(12, 0))


def test_delivery_progress_uses_evaluation_lookahead() -> None:
    """Test linear daily-budget allocation with one interval lookahead."""
    entry = _entry("05:00:00", "07:00:00")
    local_now = datetime(2026, 7, 23, 5, 0, tzinfo=UTC)
    assert delivery_progress(entry, local_now) == 0.125
    assert delivery_progress(entry, local_now.replace(hour=6), look_ahead_seconds=0) == 0.5


def test_watering_window_bounds_returns_none_outside_window() -> None:
    """Test active bounds are available only while the window is open."""
    entry = _entry("05:00:00", "22:00:00")
    assert watering_window_bounds(
        entry,
        datetime(2026, 7, 23, 3, 0, tzinfo=UTC),
    ) is None
