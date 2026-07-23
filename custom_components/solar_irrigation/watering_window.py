"""Helpers for Solar Irrigation watering-window calculations."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from .const import (
    AUTOMATIC_EVALUATION_INTERVAL_SECONDS,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
)
from .models import SolarIrrigationConfigEntry


def entry_value(entry: SolarIrrigationConfigEntry, key: str, default: Any) -> Any:
    """Read an option value while preserving explicit ``None`` overrides."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def entry_time(entry: SolarIrrigationConfigEntry, key: str, default: str) -> time:
    """Read a configured time value from effective entry configuration."""
    raw = entry_value(entry, key, default)
    if isinstance(raw, time):
        return raw
    return time.fromisoformat(str(raw))


def is_within_watering_window(
    entry: SolarIrrigationConfigEntry,
    current_time: time,
) -> bool:
    """Return whether a local time lies inside the configured watering window.

    A normal window uses an inclusive start and exclusive end. An overnight
    window wraps across midnight. Equal start and end values are rejected by
    the config flow and are treated defensively as a closed window here.
    """
    start = entry_time(
        entry,
        CONF_WATERING_WINDOW_START,
        DEFAULT_WATERING_WINDOW_START,
    )
    end = entry_time(
        entry,
        CONF_WATERING_WINDOW_END,
        DEFAULT_WATERING_WINDOW_END,
    )
    if start == end:
        return False
    if start < end:
        return start <= current_time < end
    return current_time >= start or current_time < end


def watering_window_bounds(
    entry: SolarIrrigationConfigEntry,
    local_now: datetime,
) -> tuple[datetime, datetime] | None:
    """Return the active local watering-window bounds containing ``local_now``.

    The returned datetimes use the timezone already attached to ``local_now``.
    ``None`` is returned outside the active window. Both daytime and overnight
    windows are supported.
    """
    if not is_within_watering_window(entry, local_now.timetz().replace(tzinfo=None)):
        return None

    start_time = entry_time(
        entry,
        CONF_WATERING_WINDOW_START,
        DEFAULT_WATERING_WINDOW_START,
    ).replace(tzinfo=None)
    end_time = entry_time(
        entry,
        CONF_WATERING_WINDOW_END,
        DEFAULT_WATERING_WINDOW_END,
    ).replace(tzinfo=None)
    timezone = local_now.tzinfo

    if start_time < end_time:
        return (
            datetime.combine(local_now.date(), start_time, tzinfo=timezone),
            datetime.combine(local_now.date(), end_time, tzinfo=timezone),
        )

    if local_now.time().replace(tzinfo=None) >= start_time:
        start_date = local_now.date()
        end_date = start_date + timedelta(days=1)
    else:
        end_date = local_now.date()
        start_date = end_date - timedelta(days=1)

    return (
        datetime.combine(start_date, start_time, tzinfo=timezone),
        datetime.combine(end_date, end_time, tzinfo=timezone),
    )


def delivery_progress(
    entry: SolarIrrigationConfigEntry,
    local_now: datetime,
    *,
    look_ahead_seconds: int = AUTOMATIC_EVALUATION_INTERVAL_SECONDS,
) -> float:
    """Return the fraction of today's budget that should be due by this tick.

    The automatic controller distributes the calculated daily budget across the
    watering window. A one-evaluation look-ahead means the final scheduled tick
    can make the complete daily budget due before the exclusive window end.
    """
    bounds = watering_window_bounds(entry, local_now)
    if bounds is None:
        return 0.0
    start, end = bounds
    window_seconds = (end - start).total_seconds()
    if window_seconds <= 0:
        return 0.0
    elapsed_seconds = (local_now - start).total_seconds() + max(0, look_ahead_seconds)
    return max(0.0, min(elapsed_seconds / window_seconds, 1.0))
