"""Tests for Solar Irrigation downloaded diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.coordinator import SolarIrrigationCoordinator
from custom_components.solar_irrigation.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.solar_irrigation.irrigation import SolarIrrigationController
from custom_components.solar_irrigation.models import (
    SolarIrrigationData,
    SolarIrrigationRuntimeData,
)


async def test_diagnostics_include_budget_history_and_controller(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the tuning payload contains all important internal state."""
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    coordinator.data = SolarIrrigationData(
        actual_solar_kwh=10,
        remaining_solar_kwh=20,
        expected_solar_kwh=30,
        solar_factor=0.5,
        rain_mm=None,
        rain_factor=1,
        runtime_minutes=30,
        runtime_seconds=1800,
        skip_reason=None,
        calculated_at=datetime.now(UTC),
        solar_sample_count=2,
    )
    controller = SolarIrrigationController(hass, mock_config_entry)
    controller._store.async_save = AsyncMock()
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller.state.delivered_today_seconds = 600
    controller.state.pulse_count_today = 2
    mock_config_entry.runtime_data = SolarIrrigationRuntimeData(
        coordinator=coordinator,
        controller=controller,
    )

    diagnostics = await async_get_config_entry_diagnostics(
        hass,
        mock_config_entry,
    )

    assert diagnostics["coordinator"]["expected_solar_kwh"] == 30
    assert diagnostics["water_budget"]["daily_budget_minutes"] == 30
    assert diagnostics["water_budget"]["delivered_today_minutes"] == 10
    assert diagnostics["water_budget"]["remaining_today_minutes"] == 20
    assert diagnostics["water_budget"]["pulse_count_today"] == 2
    assert "solar_history" in diagnostics
    assert "controller" in diagnostics
