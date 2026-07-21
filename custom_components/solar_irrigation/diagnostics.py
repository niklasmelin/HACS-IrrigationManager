"""Diagnostics support for Solar Irrigation config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .models import SolarIrrigationConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> dict[str, Any]:
    """Return non-secret configuration, calculation, and controller diagnostics."""
    del hass
    coordinator_data = entry.runtime_data.coordinator.data
    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "coordinator": coordinator_data.as_dict() if coordinator_data else None,
        "controller": entry.runtime_data.controller.state.as_dict(),
    }
