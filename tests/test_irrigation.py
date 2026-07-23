"""Tests for pulse-and-soak execution, safety, and daily accounting."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import (
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    ControllerStatus,
)
from custom_components.solar_irrigation.irrigation import SolarIrrigationController
from custom_components.solar_irrigation.models import SolarIrrigationData


def _data(
    *,
    runtime_seconds: int = 600,
    solar_factor: float = 1.0,
    rain_mm: float | None = None,
    rain_factor: float = 1.0,
    skip_reason: str | None = None,
) -> SolarIrrigationData:
    """Return representative coordinator data for controller tests."""
    return SolarIrrigationData(
        actual_solar_kwh=30,
        remaining_solar_kwh=35,
        expected_solar_kwh=65,
        solar_factor=solar_factor,
        rain_mm=rain_mm,
        rain_factor=rain_factor,
        runtime_minutes=runtime_seconds / 60,
        runtime_seconds=runtime_seconds,
        skip_reason=skip_reason,
        calculated_at=datetime.now(UTC),
    )


def _controller(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    data: SolarIrrigationData,
) -> tuple[SolarIrrigationController, MagicMock]:
    """Create a controller with mocked persistence and coordinator refresh."""
    controller = SolarIrrigationController(hass, entry)
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.last_update_success = True
    coordinator.last_exception = None
    coordinator.async_request_refresh = AsyncMock()
    peak_minutes = float(
        entry.options.get(
            CONF_MAX_RUNTIME,
            entry.data.get(CONF_MAX_RUNTIME, 60),
        )
    )
    coordinator.async_calculate_dry_budget_seconds = AsyncMock(
        return_value=round(data.solar_factor * peak_minutes * 60)
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=coordinator,
        controller=controller,
    )
    controller._store.async_save = AsyncMock()
    controller._entity_matches_requested_state = MagicMock(return_value=True)
    controller.state.delivery_date = dt_util.now().date().isoformat()
    return controller, coordinator


def _make_wait_instant(controller: SolarIrrigationController, calls: list[int]):
    """Return a wait replacement that advances pulse elapsed time instantly."""

    async def instant_wait(timeout_seconds: int) -> bool:
        """Record timeouts and simulate full pulse duration without sleeping."""
        calls.append(timeout_seconds)
        if controller._pulse_active and controller.state.active_started_at:
            controller.state.active_started_at -= timedelta(seconds=timeout_seconds)
        return False

    return instant_wait


async def test_new_event_rejects_an_already_active_actuator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the controller never adopts an externally active pump as its pulse."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=60))
    hass.states.async_set(controller.entity_id, "on")

    with pytest.raises(HomeAssistantError, match="already active"):
        await controller.async_run(1)

    assert not controller.is_running
    assert controller.delivered_today_seconds() == 0


async def test_zero_runtime_records_skip(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that zero runtime never turns on the irrigation entity."""
    controller, _ = _controller(
        hass,
        mock_config_entry,
        _data(runtime_seconds=0, solar_factor=0, skip_reason="no_solar"),
    )
    controller._async_turn_on_and_confirm = AsyncMock()

    assert await controller.async_run() is False

    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.last_skip_reason == "no_solar"
    controller._async_turn_on_and_confirm.assert_not_awaited()


async def test_event_is_split_into_run_soak_run_pulses(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a seven-minute event becomes three, three, and one minute pulses."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    waits: list[int] = []
    controller._async_wait_for_stop = _make_wait_instant(controller, waits)

    assert await controller.async_run(7)
    task = controller._cycle_task
    assert task is not None
    await task

    assert waits == [180, 900, 180, 900, 60]
    assert controller._async_turn_on_and_confirm.await_count == 3
    assert controller._async_turn_off_and_confirm.await_count == 3
    assert controller.delivered_today_seconds() == 420
    assert controller.pulse_count_today() == 3
    assert controller.state.requested_duration_seconds == 420
    assert controller.state.last_duration_seconds == 420
    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.last_result == "completed"


async def test_automatic_cycle_rechecks_reduced_budget_before_next_pulse(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test forecast changes cannot make an active automatic cycle exceed budget."""
    controller, coordinator = _controller(
        hass,
        mock_config_entry,
        _data(runtime_seconds=600),
    )
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._automatic_window_open = MagicMock(return_value=True)
    waits: list[int] = []
    controller._async_wait_for_stop = _make_wait_instant(controller, waits)
    refresh_count = 0

    async def refresh() -> None:
        """Reduce the daily budget after the first completed pulse."""
        nonlocal refresh_count
        refresh_count += 1
        if refresh_count == 2:
            coordinator.data = replace(
                coordinator.data,
                runtime_minutes=4,
                runtime_seconds=240,
            )

    coordinator.async_request_refresh = AsyncMock(side_effect=refresh)

    assert await controller.async_run(7, automatic=True)
    task = controller._cycle_task
    assert task is not None
    await task

    assert waits == [180, 900, 60]
    assert controller.delivered_today_seconds() == 240
    assert controller.state.requested_duration_seconds == 420
    assert controller.state.last_duration_seconds == 240
    assert coordinator.async_request_refresh.await_count == 2


async def test_manual_delivery_counts_against_later_automatic_budget(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a manual override is accumulated in the shared daily total."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(4)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.delivered_today_seconds() == 240
    assert await controller.async_run() is True
    second_task = controller._cycle_task
    assert second_task is not None
    await second_task
    assert controller.delivered_today_seconds() == 600


async def test_ignore_rain_uses_dry_budget_without_explicit_duration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test ignore_rain removes rain blocking and rain runtime reduction."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            CONF_MAX_RUNTIME: 10,
            CONF_MAX_PULSE_DURATION: 10,
        },
    )
    controller, _ = _controller(
        hass,
        mock_config_entry,
        _data(
            runtime_seconds=0,
            solar_factor=0.5,
            rain_mm=5,
            rain_factor=0,
            skip_reason="rain_threshold_reached",
        ),
    )
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(ignore_rain=True)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.delivered_today_seconds() == 300
    assert controller.state.last_result == "completed"


async def test_ignore_rain_is_harmless_without_rain_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test ignore_rain works when the optional rain input is absent."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            CONF_MAX_RUNTIME: 10,
            CONF_MAX_PULSE_DURATION: 10,
        },
    )
    controller, _ = _controller(
        hass,
        mock_config_entry,
        _data(runtime_seconds=300, solar_factor=0.5, rain_mm=None),
    )
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(ignore_rain=True)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.delivered_today_seconds() == 300


async def test_ignore_rain_uses_fresh_dry_budget_when_rain_refresh_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a failed rain refresh does not block a no-duration dry override."""
    controller, coordinator = _controller(
        hass,
        mock_config_entry,
        _data(runtime_seconds=0, solar_factor=0.5, rain_mm=5, rain_factor=0),
    )
    coordinator.data = None
    coordinator.async_calculate_dry_budget_seconds = AsyncMock(return_value=120)
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(ignore_rain=True)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.delivered_today_seconds() == 120
    coordinator.async_calculate_dry_budget_seconds.assert_awaited_once()


async def test_explicit_ignore_rain_can_run_without_calculation_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an explicit operator override does not require source data."""
    controller, coordinator = _controller(
        hass,
        mock_config_entry,
        _data(runtime_seconds=300),
    )
    coordinator.data = None
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(2, ignore_rain=True)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.delivered_today_seconds() == 120
    assert controller.state.last_result == "completed"


async def test_immediate_stop_cannot_race_with_cycle_start(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a stop immediately after start prevents orphaned watering."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()

    assert await controller.async_run(3)
    await controller.async_stop("manual_stop")

    assert controller.is_running is False
    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.decision_reason == "manual_stop"
    controller._async_turn_on_and_confirm.assert_not_awaited()


async def test_stop_during_actuator_activation_prevents_a_water_pulse(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a stop received while turn-on is pending is honored after confirmation."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    activation_started = asyncio.Event()
    release_activation = asyncio.Event()

    async def delayed_activation() -> None:
        """Hold actuator confirmation until the stop request is recorded."""
        activation_started.set()
        await release_activation.wait()

    controller._async_turn_on_and_confirm = delayed_activation
    controller._async_turn_off_and_confirm = AsyncMock()

    assert await controller.async_run(3)
    task = controller._cycle_task
    assert task is not None
    await activation_started.wait()
    stop_task = asyncio.create_task(controller.async_stop("manual_stop"))
    await asyncio.sleep(0)
    release_activation.set()
    await stop_task

    assert controller.state.last_duration_seconds == 0
    assert controller.state.status is ControllerStatus.MONITORING
    controller._async_turn_off_and_confirm.assert_awaited_once()


async def test_external_start_during_soak_stops_cycle_with_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an actuator that turns on during soak is stopped as a safety fault."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    soak_started = asyncio.Event()

    async def wait_for_external_start(timeout_seconds: int) -> bool:
        """Complete the first pulse, then block the soak until its stop event."""
        if controller._pulse_active and controller.state.active_started_at:
            controller.state.active_started_at -= timedelta(seconds=timeout_seconds)
            return False
        soak_started.set()
        assert controller._stop_event is not None
        await controller._stop_event.wait()
        return True

    controller._async_wait_for_stop = wait_for_external_start
    assert await controller.async_run(6)
    task = controller._cycle_task
    assert task is not None
    await soak_started.wait()

    hass.states.async_set(controller.entity_id, "on")
    event = MagicMock()
    event.data = {"new_state": MagicMock(state="on")}
    await controller._async_irrigation_entity_changed(event)
    await task

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.decision_reason == "irrigation_entity_active_during_soak"
    assert "expected it to remain off" in (controller.state.last_error or "")
    controller._async_turn_off_and_confirm.assert_awaited()


async def test_external_pump_off_reconciles_and_accounts_elapsed_time(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an external off ends the pulse and preserves delivered runtime."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    pulse_started = asyncio.Event()

    async def wait_until_external_stop(timeout_seconds: int) -> bool:
        """Block the pulse until the test sends a state-change stop."""
        del timeout_seconds
        if controller._pulse_active:
            pulse_started.set()
            assert controller._stop_event is not None
            await controller._stop_event.wait()
            assert controller.state.active_started_at is not None
            controller.state.active_started_at -= timedelta(seconds=30)
            return True
        return False

    controller._async_wait_for_stop = wait_until_external_stop
    assert await controller.async_run(3)
    task = controller._cycle_task
    assert task is not None
    await pulse_started.wait()

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}
    await controller._async_irrigation_entity_changed(event)
    await task

    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.decision_reason == "irrigation_entity_turned_off"
    assert controller.delivered_today_seconds() == 30
    controller._async_turn_off_and_confirm.assert_not_awaited()


async def test_unavailable_pump_reconciles_to_visible_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test actuator unavailability ends the cycle and displays its error."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()
    pulse_started = asyncio.Event()

    async def wait_until_unavailable(timeout_seconds: int) -> bool:
        """Block until the unavailable event requests a stop."""
        del timeout_seconds
        if controller._pulse_active:
            pulse_started.set()
            assert controller._stop_event is not None
            await controller._stop_event.wait()
            assert controller.state.active_started_at is not None
            controller.state.active_started_at -= timedelta(seconds=20)
            return True
        return False

    controller._async_wait_for_stop = wait_until_unavailable
    assert await controller.async_run(3)
    task = controller._cycle_task
    assert task is not None
    await pulse_started.wait()

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="unavailable")}
    await controller._async_irrigation_entity_changed(event)
    await task

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.decision_reason == "irrigation_entity_unavailable"
    assert controller.state.last_error == "Irrigation entity became unavailable"
    assert controller.delivered_today_seconds() == 20


async def test_status_remains_irrigating_until_stop_is_confirmed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test status never reports soaking while the actuator may still be on."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=60))
    controller._async_turn_on_and_confirm = AsyncMock()
    stop_started = asyncio.Event()
    allow_stop_confirmation = asyncio.Event()

    async def delayed_stop_confirmation() -> None:
        """Hold the physical-stop confirmation until assertions are complete."""
        stop_started.set()
        await allow_stop_confirmation.wait()

    controller._async_turn_off_and_confirm = AsyncMock(
        side_effect=delayed_stop_confirmation
    )
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(1)
    task = controller._cycle_task
    assert task is not None
    await stop_started.wait()

    assert controller.state.status is ControllerStatus.IRRIGATING
    assert controller.is_irrigating
    assert controller.state.decision_reason == "stopping_irrigation_pulse"

    allow_stop_confirmation.set()
    await task
    assert controller.state.status is ControllerStatus.MONITORING
    assert not controller.is_irrigating


async def test_external_off_after_failed_stop_accounts_complete_pulse(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a later physical off finalizes time retained after stop failure."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=60))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock(
        side_effect=HomeAssistantError("relay did not turn off")
    )
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(1)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.is_irrigating
    assert controller.delivered_today_seconds() == 0
    assert controller.state.active_started_at is not None

    event = MagicMock()
    event.data = {"new_state": MagicMock(state="off")}
    await controller._async_irrigation_entity_changed(event)

    assert controller.state.status is ControllerStatus.MONITORING
    assert not controller.is_irrigating
    assert controller.delivered_today_seconds() == 60
    assert controller.state.last_duration_seconds == 60


async def test_turn_off_failure_remains_an_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the controller never claims monitoring after a failed stop command."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=60))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock(
        side_effect=HomeAssistantError("relay did not turn off")
    )
    controller._async_wait_for_stop = _make_wait_instant(controller, [])

    assert await controller.async_run(1)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.last_result == "failed"
    assert "relay did not turn off" in (controller.state.last_error or "")


async def test_restart_recovery_accounts_interrupted_pulse(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test restart recovery adds elapsed pulse time before clearing active state."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    now = dt_util.utcnow()
    controller.state.status = ControllerStatus.IRRIGATING
    controller.state.active_started_at = now - timedelta(seconds=120)
    controller.state.active_end_at = now + timedelta(seconds=60)
    controller.state.current_pulse_requested_seconds = 180
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller._store.async_load = AsyncMock(return_value=controller.state.as_dict())
    controller._async_turn_off_and_confirm = AsyncMock()

    await controller.async_load()

    assert 119 <= controller.delivered_today_seconds() <= 121
    assert controller.state.last_result == "interrupted"
    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.active_started_at is None


async def test_restart_recovery_counts_time_beyond_requested_when_actuator_is_active(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an actuator still on at restart is counted through confirmed stop."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    now = dt_util.utcnow()
    controller.state.status = ControllerStatus.IRRIGATING
    controller.state.active_started_at = now - timedelta(seconds=300)
    controller.state.active_end_at = now - timedelta(seconds=240)
    controller.state.current_pulse_requested_seconds = 60
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller._store.async_load = AsyncMock(return_value=controller.state.as_dict())
    controller._async_turn_off_and_confirm = AsyncMock()
    hass.states.async_set(controller.entity_id, "on")

    await controller.async_load()

    assert controller.delivered_today_seconds() >= 300
    assert controller.state.last_duration_seconds >= 300
    assert controller.state.status is ControllerStatus.MONITORING


async def test_restart_recovery_counts_persisted_stop_failure_conservatively(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test unknown off time after a stop failure is counted through restart."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    now = dt_util.utcnow()
    controller.state.status = ControllerStatus.ERROR
    controller.state.active_started_at = now - timedelta(seconds=300)
    controller.state.active_end_at = now - timedelta(seconds=240)
    controller.state.current_pulse_requested_seconds = 60
    controller.state.last_error = "Previous stop failed"
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller._store.async_load = AsyncMock(return_value=controller.state.as_dict())
    hass.states.async_set(controller.entity_id, "off")

    await controller.async_load()

    assert controller.delivered_today_seconds() >= 300
    assert controller.state.last_result == "interrupted"
    assert controller.state.status is ControllerStatus.MONITORING


async def test_restart_stop_failure_preserves_active_timing_for_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test failed restart recovery retains time until a later confirmed stop."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    now = dt_util.utcnow()
    controller.state.status = ControllerStatus.IRRIGATING
    controller.state.active_started_at = now - timedelta(seconds=60)
    controller.state.active_end_at = now + timedelta(seconds=120)
    controller.state.current_pulse_requested_seconds = 180
    controller.state.delivery_date = dt_util.now().date().isoformat()
    controller._store.async_load = AsyncMock(return_value=controller.state.as_dict())
    controller._async_turn_off_and_confirm = AsyncMock(
        side_effect=HomeAssistantError("relay unavailable")
    )

    await controller.async_load()

    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.active_started_at is not None
    assert controller.is_irrigating
    assert controller.delivered_today_seconds() == 0

    controller._async_turn_off_and_confirm = AsyncMock()
    await controller.async_stop("manual_recovery")

    assert controller.state.status is ControllerStatus.MONITORING
    assert not controller.is_irrigating
    assert controller.delivered_today_seconds() >= 60


async def test_requested_and_actual_duration_are_separate(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an interrupted event records requested and actual runtime separately."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    controller._async_turn_on_and_confirm = AsyncMock()
    controller._async_turn_off_and_confirm = AsyncMock()

    async def stop_after_one_minute(timeout_seconds: int) -> bool:
        """Simulate a manual stop one minute into the first pulse."""
        del timeout_seconds
        if controller._pulse_active:
            assert controller.state.active_started_at is not None
            controller.state.active_started_at -= timedelta(seconds=60)
            controller._stop_reason = "manual_stop"
            assert controller._stop_event is not None
            controller._stop_event.set()
            return True
        return False

    controller._async_wait_for_stop = stop_after_one_minute
    assert await controller.async_run(3)
    task = controller._cycle_task
    assert task is not None
    await task

    assert controller.state.requested_duration_seconds == 180
    assert controller.state.last_duration_seconds == 60
    assert controller.state.last_result == "stopped"


async def test_controller_push_listener_and_sticky_error_behavior(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test immediate observability and source-only automatic error recovery."""
    controller, _ = _controller(hass, mock_config_entry, _data(runtime_seconds=600))
    listener = MagicMock()
    remove = controller.async_add_listener(listener)

    await controller.async_set_status(
        ControllerStatus.ERROR,
        decision_reason="irrigation_stop_failed",
        error_message="Pump remains active",
    )
    await controller.async_set_status(
        ControllerStatus.MONITORING,
        decision_reason="automatic_window_open",
        clear_error=True,
    )
    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.last_error == "Pump remains active"

    await controller.async_set_status(
        ControllerStatus.ERROR,
        decision_reason="source_data_unavailable",
        error_message="Forecast unavailable",
    )
    await controller.async_set_status(
        ControllerStatus.MONITORING,
        decision_reason="automatic_window_open",
        clear_error=True,
    )
    assert controller.state.status is ControllerStatus.ERROR
    assert controller.state.last_error == "Pump remains active"

    controller.state.status = ControllerStatus.MONITORING
    controller.state.decision_reason = "automatic_window_open"
    controller.state.last_error = None
    await controller.async_set_status(
        ControllerStatus.ERROR,
        decision_reason="source_data_unavailable",
        error_message="Forecast unavailable",
    )
    await controller.async_set_status(
        ControllerStatus.MONITORING,
        decision_reason="automatic_window_open",
        clear_error=True,
    )
    assert controller.state.status is ControllerStatus.MONITORING
    assert controller.state.last_error is None
    assert listener.call_count == 3

    remove()
