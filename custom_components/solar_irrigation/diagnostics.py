"""Diagnostics support for Solar Irrigation config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    CONF_SOAK_DURATION,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_SOAK_DURATION,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
)
from .models import SolarIrrigationConfigEntry
from .watering_window import entry_value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> dict[str, Any]:
    """Return configuration, calculation, history, and controller diagnostics."""
    del hass
    coordinator = entry.runtime_data.coordinator
    coordinator_data = coordinator.data
    controller = entry.runtime_data.controller
    delivered_minutes = round(controller.delivered_today_seconds() / 60, 3)
    budget_minutes = coordinator_data.runtime_minutes if coordinator_data else 0.0
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "effective_delivery_settings": {
            "peak_daily_water_demand_minutes": float(
                entry_value(entry, CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
            ),
            "maximum_pulse_minutes": float(
                entry_value(
                    entry,
                    CONF_MAX_PULSE_DURATION,
                    DEFAULT_MAX_PULSE_DURATION,
                )
            ),
            "soak_minutes": float(
                entry_value(entry, CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION)
            ),
            "watering_window_start": str(
                entry_value(
                    entry,
                    CONF_WATERING_WINDOW_START,
                    DEFAULT_WATERING_WINDOW_START,
                )
            ),
            "watering_window_end": str(
                entry_value(
                    entry,
                    CONF_WATERING_WINDOW_END,
                    DEFAULT_WATERING_WINDOW_END,
                )
            ),
        },
        "coordinator": coordinator_data.as_dict() if coordinator_data else None,
        "solar_history": coordinator.solar_history_as_dict(),
        "water_budget": {
            "daily_budget_minutes": budget_minutes,
            "delivered_today_minutes": delivered_minutes,
            "remaining_today_minutes": round(
                max(0.0, budget_minutes - delivered_minutes),
                3,
            ),
            "pulse_count_today": controller.pulse_count_today(),
        },
        "controller": {
            **controller.state.as_dict(),
            "is_running_or_soaking": controller.is_running,
            "is_actively_irrigating": controller.is_irrigating,
            "actuator_state": controller.actuator_state,
            "actuator_is_active": controller.actuator_is_active,
        },
    }
