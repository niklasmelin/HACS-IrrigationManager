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


async def test_external_pump_off_reconciles_irrigating_status(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that an externally stopped pump clears the irrigating status."""
    controller = SolarIrrigationController(hass, mock_config_entry)
    controller._store.async_save = AsyncMock()
    controller.state.status = ControllerStatus.IRRIGATING
    controller.state.active_started_at = datetime.now(UTC)
    controller._run_task = hass.async_create_task(
        __import__("asyncio").sleep(3600),
        "test_irrigation_timer",
    )

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}

    await controller._async_irrigation_entity_changed(event)

    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.decision_reason == "irrigation_entity_turned_off"
    assert controller.state.active_started_at is None
    assert controller.state.active_end_at is None
    assert controller.is_running is False


async def test_unavailable_pump_reconciles_to_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that an unavailable pump ends the run and exposes an error."""
    controller = SolarIrrigationController(hass, mock_config_entry)
    controller._store.async_save = AsyncMock()
    controller.state.status = ControllerStatus.IRRIGATING
    controller.state.active_started_at = datetime.now(UTC)
    controller._run_task = hass.async_create_task(
        __import__("asyncio").sleep(3600),
        "test_irrigation_timer",
    )

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="unavailable")}

    await controller._async_irrigation_entity_changed(event)

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.decision_reason == "irrigation_entity_unavailable"
    assert controller.state.last_error == "Irrigation entity became unavailable"
    assert controller.is_running is False
