"""Tests for safe irrigation execution behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import ControllerStatus
from custom_components.solar_irrigation.irrigation import SolarIrrigationController
from custom_components.solar_irrigation.models import SolarIrrigationData


async def test_zero_runtime_records_skip(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that zero runtime never turns on the irrigation entity."""
    controller = SolarIrrigationController(hass, mock_config_entry)
    coordinator = MagicMock()
    coordinator.data = SolarIrrigationData(
        actual_solar_kwh=0,
        remaining_solar_kwh=0,
        expected_solar_kwh=0,
        solar_factor=0,
        rain_mm=None,
        rain_factor=1,
        runtime_minutes=0,
        runtime_seconds=0,
        skip_reason="no_solar",
        calculated_at=datetime.now(UTC),
    )
    mock_config_entry.runtime_data = MagicMock(coordinator=coordinator, controller=controller)
    controller._store.async_save = AsyncMock()
    assert await controller.async_run() is False
    assert controller.state.status is ControllerStatus.COMPLETED
    assert controller.state.last_skip_reason == "no_solar"
