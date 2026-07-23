"""Tests for controller observability and push-updated sensor values."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import ControllerStatus
from custom_components.solar_irrigation.coordinator import SolarIrrigationCoordinator
from custom_components.solar_irrigation.irrigation import SolarIrrigationController
from custom_components.solar_irrigation.models import (
    SolarIrrigationData,
    SolarIrrigationRuntimeData,
)
from custom_components.solar_irrigation.sensor import (
    DecisionReasonSensor,
    RemainingBudgetSensor,
    SolarIrrigationStatusSensor,
)


def _attach_runtime(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> tuple[SolarIrrigationCoordinator, SolarIrrigationController]:
    """Attach real coordinator and controller objects with deterministic data."""
    coordinator = SolarIrrigationCoordinator(hass, entry)
    # These tests verify controller push updates, not periodic coordinator
    # scheduling. Disable the refresh interval before an entity listener is
    # attached so the test cannot leave a DataUpdateCoordinator timer behind.
    coordinator.update_interval = None
    coordinator.data = SolarIrrigationData(
        actual_solar_kwh=20,
        remaining_solar_kwh=20,
        expected_solar_kwh=40,
        solar_factor=0.5,
        rain_mm=None,
        rain_factor=1,
        runtime_minutes=30,
        runtime_seconds=1800,
        skip_reason=None,
        calculated_at=datetime.now(UTC),
        solar_sample_count=4,
    )
    controller = SolarIrrigationController(hass, entry)
    controller._store.async_save = AsyncMock()
    entry.runtime_data = SolarIrrigationRuntimeData(
        coordinator=coordinator,
        controller=controller,
    )
    return coordinator, controller


async def test_controller_sensor_subscribes_to_push_updates(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test controller changes write entity state without waiting for polling."""
    _, controller = _attach_runtime(hass, mock_config_entry)
    sensor = SolarIrrigationStatusSensor(mock_config_entry)
    sensor.hass = hass
    sensor.async_write_ha_state = MagicMock()

    await sensor.async_added_to_hass()
    try:
        await controller.async_set_status(
            ControllerStatus.SOAKING,
            decision_reason="soil_soaking",
        )

        sensor.async_write_ha_state.assert_called_once()
        assert sensor.native_value == "soaking"
        assert sensor.extra_state_attributes["decision_reason"] == "soil_soaking"
    finally:
        await sensor.async_will_remove_from_hass()


async def test_error_message_and_budget_are_observable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test diagnostics expose an actual error and the shared remaining budget."""
    _, controller = _attach_runtime(hass, mock_config_entry)
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller.state.delivered_today_seconds = 600
    controller.state.status = ControllerStatus.ERROR
    controller.state.decision_reason = "irrigation_stop_failed"
    controller.state.last_error = "Pump did not turn off"

    status = SolarIrrigationStatusSensor(mock_config_entry)
    reason = DecisionReasonSensor(mock_config_entry)
    remaining = RemainingBudgetSensor(mock_config_entry)

    assert status.native_value == "error"
    assert status.extra_state_attributes["error_message"] == "Pump did not turn off"
    assert reason.native_value == "Pump did not turn off"
    assert reason.extra_state_attributes["error_message"] == "Pump did not turn off"
    assert remaining.native_value == 20
