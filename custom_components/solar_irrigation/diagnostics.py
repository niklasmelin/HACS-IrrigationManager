"""Diagnostics support for Solar Irrigation config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .models import SolarIrrigationConfigEntry


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
        "coordinator": coordinator_data.as_dict() if coordinator_data else None,
        "solar_history": coordinator.solar_history_as_dict(),
        "water_budget": {
            "daily_budget_minutes": budget_minutes,
            "delivered_today_minutes": delivered_minutes,
            "remaining_today_minutes": round(
                max(0.0, budget_minutes - delivered_minutes), 3
            ),
            "pulse_count_today": controller.pulse_count_today(),
        },
        "controller": controller.state.as_dict(),
    }
