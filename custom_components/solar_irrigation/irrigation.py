"""Pulse-and-soak irrigation execution, accounting, and persistence."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTUATOR_CONFIRM_TIMEOUT_SECONDS,
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    CONF_SOAK_DURATION,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_SOAK_DURATION,
    MAX_MAX_PULSE_DURATION,
    MAX_SOAK_DURATION,
    MIN_MAX_PULSE_DURATION,
    MIN_SOAK_DURATION,
    MINUTES_TO_SECONDS,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
    ControllerStatus,
)
from .models import SolarIrrigationConfigEntry, SolarIrrigationControllerState
from .watering_window import entry_value, is_within_watering_window

_LOGGER = logging.getLogger(__name__)

_RECOVERABLE_SOURCE_ERRORS = frozenset({"source_data_unavailable"})


class SolarIrrigationController:
    """Control one irrigation actuator as serialized run-soak pulse cycles.

    A watering event consists of one or more short pump-on pulses separated by a
    configured pump-off soak interval. The same task owns the complete event,
    including soak periods, so neither the periodic scheduler nor a manual action
    can start an overlapping event. Confirmed pump-on time from manual and
    automatic events is accumulated in one local-day delivery counter.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SolarIrrigationConfigEntry,
    ) -> None:
        """Initialize locking, event state, listeners, and persistent storage."""
        self.hass = hass
        self.entry = entry
        self.state = SolarIrrigationControllerState()
        self._lock = asyncio.Lock()
        self._cycle_task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._stop_reason: str | None = None
        self._stop_error: str | None = None
        self._entity_already_inactive = False
        self._pulse_active = False
        self._activation_in_progress = False
        self._deactivation_in_progress = False
        self._remove_entity_listener: Callable[[], None] | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._store: Store[dict[str, object]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
        )

    @property
    def entity_id(self) -> str:
        """Return the configured irrigation switch or valve entity ID."""
        return str(entry_value(self.entry, CONF_IRRIGATION_ENTITY, ""))

    @property
    def actuator_state(self) -> str:
        """Return the current Home Assistant state of the irrigation actuator."""
        current = self.hass.states.get(self.entity_id)
        return current.state if current is not None else "missing"

    @property
    def actuator_is_active(self) -> bool:
        """Return whether the physical actuator currently reports water flow."""
        return self._actual_entity_is_active()

    @property
    def is_running(self) -> bool:
        """Return whether a complete watering event is running or soaking."""
        return self._cycle_task is not None and not self._cycle_task.done()

    @property
    def is_irrigating(self) -> bool:
        """Return whether the actuator is expected to be delivering water."""
        return self._pulse_active or self.state.status is ControllerStatus.IRRIGATING

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a push listener for controller-state changes."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            """Remove one previously registered controller-state listener."""
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _notify_listeners(self) -> None:
        """Notify controller-backed entities after an in-memory state change."""
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:  # pragma: no cover - entity callback isolation
                _LOGGER.exception("Controller state listener failed")

    async def async_load(self) -> None:
        """Load state, account interrupted watering, and restore a safe actuator.

        If Home Assistant restarted during a confirmed pulse, elapsed delivery is
        reconstructed from persisted timing. A still-active actuator or prior stop
        failure is conservatively counted through confirmed recovery; an already
        inactive actuator is capped at the planned pulse end. A persisted error
        remains visible until the corresponding problem is deliberately recovered.
        """
        stored = await self._store.async_load()
        if stored:
            self.state = SolarIrrigationControllerState.from_dict(stored)

        loaded_status = self.state.status
        self._reset_daily_delivery_if_needed()
        now = dt_util.utcnow()
        actual_active = self._actual_entity_is_active()
        interrupted = loaded_status in {
            ControllerStatus.IRRIGATING,
            ControllerStatus.SOAKING,
            ControllerStatus.WAITING_FOR_PULSE,
        } or self.state.active_started_at is not None
        recovery_completed_at = now

        if actual_active or loaded_status is ControllerStatus.IRRIGATING:
            try:
                await self._async_turn_off_and_confirm()
                recovery_completed_at = dt_util.utcnow()
            except HomeAssistantError as err:
                self.state.status = ControllerStatus.ERROR
                self.state.last_error = str(err)
                self.state.decision_reason = "restart_recovery_failed"
                self.state.last_result = "failed"
                self.state.last_execution = now
                # The actuator may still be delivering water. Keep the persisted
                # pulse timing so a later stop or external-off event can account
                # the complete interval rather than losing it during recovery.
                self._pulse_active = True
                await self._async_save()
                return

        recovered_seconds = self._recover_active_pulse_seconds(
            recovery_completed_at,
            conservatively_assume_active=(
                actual_active
                or (
                    loaded_status is ControllerStatus.ERROR
                    and self.state.active_started_at is not None
                )
            ),
        )
        if recovered_seconds:
            self.state.delivered_today_seconds += recovered_seconds
            self.state.last_duration_seconds += recovered_seconds

        if actual_active and not interrupted:
            self.state.status = ControllerStatus.ERROR
            self.state.last_error = (
                "Irrigation entity was active without a controller-owned event"
            )
            self.state.decision_reason = "unexpected_active_entity_on_startup"
            self.state.last_result = "failed"
            self.state.last_execution = now
        elif interrupted:
            self.state.status = ControllerStatus.MONITORING
            self.state.last_error = None
            self.state.decision_reason = "restart_recovery_completed"
            self.state.last_result = "interrupted"
            self.state.last_execution = now
        elif loaded_status is ControllerStatus.ERROR:
            # Keep an actuator or source error observable across a restart.
            self.state.status = ControllerStatus.ERROR
        else:
            self.state.status = ControllerStatus.MONITORING
            self.state.last_error = None
            self.state.decision_reason = "controller_initialized"

        self._clear_active_cycle_state()
        await self._async_save()

    async def async_start_monitoring(self) -> None:
        """Subscribe to physical actuator state changes for reconciliation."""
        if self._remove_entity_listener is not None:
            return
        self._remove_entity_listener = async_track_state_change_event(
            self.hass,
            [self.entity_id],
            self._async_irrigation_entity_changed,
        )

    async def _async_irrigation_entity_changed(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Reconcile an actuator state change with the active pulse cycle.

        An unexpected off state ends the current event and accounts elapsed water.
        Unknown or unavailable states also end the event, request a best-effort
        stop, and expose an error. An actuator that turns on outside a
        controller-owned event is stopped immediately for safety.
        """
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        command_in_progress = (
            self._activation_in_progress or self._deactivation_in_progress
        )
        if self._pulse_active:
            if new_state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
                if self.is_running:
                    await self._request_cycle_stop(
                        "irrigation_entity_unavailable",
                        error=f"Irrigation entity became {new_state.state}",
                        entity_already_inactive=False,
                    )
                else:
                    await self._async_finalize_orphaned_pulse(
                        "irrigation_entity_unavailable",
                        error=f"Irrigation entity became {new_state.state}",
                        entity_already_inactive=False,
                    )
                return
            if not self._entity_state_is_active(new_state.state):
                # Ignore the inactive state produced by our own confirmed stop.
                # The command waiter and pulse task perform the accounting.
                if self._deactivation_in_progress:
                    return
                if self.is_running:
                    await self._request_cycle_stop(
                        "irrigation_entity_turned_off",
                        entity_already_inactive=True,
                    )
                else:
                    await self._async_finalize_orphaned_pulse(
                        "irrigation_entity_turned_off",
                        entity_already_inactive=True,
                    )
                return

        if self.is_running and not self._pulse_active and not command_in_progress:
            if new_state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
                await self._request_cycle_stop(
                    "irrigation_entity_unavailable_during_cycle",
                    error=(
                        "Irrigation entity became "
                        f"{new_state.state} while waiting between pulses"
                    ),
                    entity_already_inactive=False,
                )
                return
            if self._entity_state_is_active(new_state.state):
                await self._request_cycle_stop(
                    "irrigation_entity_active_during_soak",
                    error=(
                        "Irrigation entity became active while the controller "
                        "expected it to remain off"
                    ),
                    entity_already_inactive=False,
                )
                return

        if (
            not self.is_running
            and not command_in_progress
            and self._entity_state_is_active(new_state.state)
        ):
            await self._async_handle_unexpected_external_start()


    async def _async_finalize_orphaned_pulse(
        self,
        reason: str,
        *,
        error: str | None = None,
        entity_already_inactive: bool,
    ) -> None:
        """Finalize a persisted active pulse after its cycle task has ended.

        A failed stop can leave the actuator active while the owning event task has
        already completed with an error. A later physical off or unavailable event
        must still account all elapsed pump-on time and update the observable state.
        """
        stop_error = error
        stopped_at = dt_util.utcnow()
        actuator_confirmed_off = entity_already_inactive
        if not entity_already_inactive:
            try:
                await self._async_turn_off_and_confirm()
                stopped_at = dt_util.utcnow()
                actuator_confirmed_off = True
            except HomeAssistantError as err:
                stop_error = str(err)

        async with self._lock:
            delivered_seconds = self._active_pulse_elapsed_seconds(stopped_at)
            if actuator_confirmed_off:
                self._account_delivery(delivered_seconds, stopped_at)
                self._clear_active_cycle_state()
                self.state.last_duration_seconds += delivered_seconds
            else:
                self._pulse_active = True
            self.state.last_execution = stopped_at
            self.state.last_result = "failed" if stop_error else "stopped"
            self.state.last_error = stop_error
            self.state.status = (
                ControllerStatus.ERROR if stop_error else ControllerStatus.MONITORING
            )
            self.state.decision_reason = (
                "irrigation_stop_failed"
                if not actuator_confirmed_off
                else reason
            )
            await self._async_save()

    async def _async_handle_unexpected_external_start(self) -> None:
        """Stop an externally started actuator and expose the safety incident."""
        try:
            await self._async_turn_off_and_confirm()
            message = "Irrigation entity was turned on outside Solar Irrigation"
        except HomeAssistantError as err:
            message = f"Unexpected irrigation start could not be stopped: {err}"
        async with self._lock:
            self.state.status = ControllerStatus.ERROR
            self.state.last_error = message
            self.state.decision_reason = "irrigation_entity_turned_on_externally"
            self.state.last_result = "failed"
            self.state.last_execution = dt_util.utcnow()
            await self._async_save()

    def _entity_state_is_active(self, state: str) -> bool:
        """Return whether an entity state means that irrigation is active."""
        domain = self.entity_id.split(".", 1)[0]
        if domain == "valve":
            # A closing valve can still pass water and is not yet a confirmed
            # inactive state. Treat it as active until Home Assistant reports
            # the final ``closed`` state.
            return state in {"open", "opening", "closing"}
        return state == STATE_ON

    def _actual_entity_is_active(self) -> bool:
        """Return whether the current Home Assistant actuator state is active."""
        current = self.hass.states.get(self.entity_id)
        return current is not None and self._entity_state_is_active(current.state)

    async def async_run(
        self,
        duration_minutes: float | None = None,
        *,
        automatic: bool = False,
        ignore_rain: bool = False,
    ) -> bool:
        """Start one non-overlapping pulse-and-soak watering event.

        An explicit manual duration is an operator override and may exceed the
        automatic budget, but its confirmed delivery is still accumulated for the
        day. An automatic duration is always clamped to the remaining budget.
        Without an explicit duration, the event uses the remaining current budget.
        ``ignore_rain`` removes both rain reduction and the rain stop condition and
        works the same whether or not a rain sensor is configured.
        """
        async with self._lock:
            daily_reset = self._reset_daily_delivery_if_needed()
            if self.is_running:
                raise HomeAssistantError("An irrigation event is already running")
            if self._actual_entity_is_active():
                raise HomeAssistantError(
                    f"Irrigation entity {self.entity_id} is already active outside "
                    "a controller-owned event; stop it before starting a new event"
                )
            coordinator = self.entry.runtime_data.coordinator
            data = coordinator.data
            if data is None and not ignore_rain:
                raise HomeAssistantError("Irrigation calculation data is unavailable")

            if (
                data is not None
                and data.rain_mm is not None
                and data.rain_factor <= 0
                and not ignore_rain
            ):
                await self._record_skip_locked(
                    data.skip_reason or "rain_threshold_reached"
                )
                return False

            if duration_minutes is None:
                delivered_seconds = self.state.delivered_today_seconds
                if ignore_rain:
                    try:
                        budget_seconds = (
                            await coordinator.async_calculate_dry_budget_seconds()
                        )
                    except Exception as err:
                        raise HomeAssistantError(
                            f"Dry irrigation budget could not be calculated: {err}"
                        ) from err
                else:
                    budget_seconds = self._available_budget_seconds(ignore_rain=False)
                duration_seconds = max(0, budget_seconds - delivered_seconds)
            else:
                requested_seconds = round(
                    float(duration_minutes) * MINUTES_TO_SECONDS
                )
                if automatic:
                    delivered_seconds = self.state.delivered_today_seconds
                    if ignore_rain:
                        try:
                            budget_seconds = (
                                await coordinator.async_calculate_dry_budget_seconds()
                            )
                        except Exception as err:
                            raise HomeAssistantError(
                                f"Dry irrigation budget could not be calculated: {err}"
                            ) from err
                    else:
                        budget_seconds = self._available_budget_seconds(
                            ignore_rain=False
                        )
                    duration_seconds = min(
                        requested_seconds,
                        max(0, budget_seconds - delivered_seconds),
                    )
                else:
                    duration_seconds = requested_seconds

            if duration_seconds <= 0:
                reason = (
                    data.skip_reason
                    if data is not None and data.skip_reason
                    else "daily_budget_exhausted"
                )
                await self._record_skip_locked(reason)
                return False

            self._stop_event = asyncio.Event()
            self._stop_reason = None
            self._stop_error = None
            self._entity_already_inactive = False
            self.state.status = ControllerStatus.WAITING_FOR_PULSE
            self.state.requested_duration_seconds = duration_seconds
            self.state.current_pulse_requested_seconds = 0
            self.state.cycle_remaining_seconds = duration_seconds
            self.state.last_duration_seconds = 0
            self.state.last_result = None
            self.state.last_skip_reason = None
            # Preserve a prior actuator error while a retry is only scheduled.
            # The error is cleared below only after the actuator is confirmed on.
            self.state.decision_reason = (
                "automatic_cycle_scheduled" if automatic else "manual_cycle_scheduled"
            )
            self.state.next_pulse_at = dt_util.utcnow()
            if daily_reset:
                _LOGGER.debug("Reset daily delivery counters before starting event")
            await self._async_save()
            task = self.hass.async_create_task(
                self._async_run_cycle(
                    duration_seconds,
                    automatic=automatic,
                    ignore_rain=ignore_rain,
                ),
                "solar_irrigation_cycle",
            )
            self._cycle_task = task
            return True

    async def async_stop(
        self,
        reason: str = "manual_stop",
        *,
        error: str | None = None,
    ) -> None:
        """Stop an active event or safely stop an orphaned active actuator."""
        async with self._lock:
            task = self._cycle_task
            if task is not None and not task.done():
                self._stop_reason = reason
                self._stop_error = error
                if self._stop_event is not None:
                    self._stop_event.set()
            else:
                task = None

        if task is not None:
            with suppress(asyncio.CancelledError):
                await task
            return

        if self._actual_entity_is_active() or self.is_irrigating:
            stop_error = error
            stopped_at = dt_util.utcnow()
            actuator_confirmed_off = False
            try:
                await self._async_turn_off_and_confirm()
                stopped_at = dt_util.utcnow()
                actuator_confirmed_off = True
            except HomeAssistantError as err:
                stop_error = str(err)

            async with self._lock:
                delivered_seconds = self._active_pulse_elapsed_seconds(stopped_at)
                if actuator_confirmed_off:
                    self._account_delivery(delivered_seconds, stopped_at)
                    self._clear_active_cycle_state()
                    self.state.last_duration_seconds += delivered_seconds
                else:
                    # Preserve active timing fields when the actuator could not be
                    # confirmed off. A later stop, external off, or restart can then
                    # account the complete physical pump-on interval. Unconfirmed
                    # time is not added to the actual-duration field yet.
                    self._pulse_active = True
                self.state.last_execution = stopped_at
                self.state.last_result = "failed" if stop_error else "stopped"
                self.state.last_error = stop_error
                self.state.status = (
                    ControllerStatus.ERROR
                    if stop_error
                    else ControllerStatus.MONITORING
                )
                self.state.decision_reason = (
                    "irrigation_stop_failed"
                    if not actuator_confirmed_off
                    else reason
                )
                await self._async_save()

    async def _request_cycle_stop(
        self,
        reason: str,
        *,
        error: str | None = None,
        entity_already_inactive: bool = False,
    ) -> None:
        """Request that the active cycle stop at its next safe await point."""
        async with self._lock:
            if not self.is_running:
                return
            self._stop_reason = reason
            self._stop_error = error
            self._entity_already_inactive = entity_already_inactive
            if self._stop_event is not None:
                self._stop_event.set()

    async def _async_run_cycle(
        self,
        requested_seconds: int,
        *,
        automatic: bool,
        ignore_rain: bool,
    ) -> None:
        """Deliver one event through short pulses separated by soak intervals.

        The initial event-loop checkpoint gives an immediate stop request a chance
        to mark the newly scheduled event before any actuator command is issued.
        This closes the small race between returning from ``async_run`` and the
        background cycle beginning its first pulse.
        """
        await asyncio.sleep(0)
        remaining_seconds = requested_seconds
        delivered_event_seconds = 0
        final_status = ControllerStatus.MONITORING
        final_reason = "cycle_completed"
        final_result = "completed"
        final_error: str | None = None

        try:
            while remaining_seconds > 0:
                if self._stop_requested:
                    final_status, final_reason, final_result, final_error = (
                        self._requested_stop_outcome()
                    )
                    break

                if automatic:
                    (
                        remaining_seconds,
                        stop_status,
                        stop_reason,
                        stop_result,
                        stop_error,
                    ) = await self._async_automatic_continuation_outcome(
                        remaining_seconds,
                        ignore_rain=ignore_rain,
                    )
                    if stop_status is not None:
                        final_status = stop_status
                        final_reason = stop_reason
                        final_result = stop_result
                        final_error = stop_error
                        break

                pulse_seconds = min(self._max_pulse_seconds, remaining_seconds)
                pulse_delivered, stopped_early = await self._async_execute_pulse(
                    pulse_seconds
                )
                delivered_event_seconds += pulse_delivered
                remaining_seconds = max(0, remaining_seconds - pulse_delivered)

                async with self._lock:
                    self.state.last_duration_seconds = delivered_event_seconds
                    self.state.cycle_remaining_seconds = remaining_seconds
                    await self._async_save()

                if stopped_early or self._stop_requested:
                    final_status, final_reason, final_result, final_error = (
                        self._requested_stop_outcome()
                    )
                    break
                if pulse_delivered <= 0:
                    raise HomeAssistantError(
                        "Irrigation pulse delivered no measurable runtime"
                    )
                if remaining_seconds <= 0:
                    break

                if automatic and not self._automatic_window_open():
                    final_status = ControllerStatus.SLEEPING
                    final_reason = "watering_window_closed"
                    final_result = "partial"
                    break

                async with self._lock:
                    soak_seconds = self._soak_seconds
                    self.state.status = ControllerStatus.SOAKING
                    self.state.decision_reason = "soil_soaking"
                    self.state.next_pulse_at = dt_util.utcnow() + timedelta(
                        seconds=soak_seconds
                    )
                    await self._async_save()
                if await self._async_wait_for_stop(soak_seconds):
                    final_status, final_reason, final_result, final_error = (
                        self._requested_stop_outcome()
                    )
                    break

        except HomeAssistantError as err:
            final_status = ControllerStatus.ERROR
            final_reason = "irrigation_cycle_failed"
            final_result = "failed"
            final_error = str(err)
            _LOGGER.error("Irrigation cycle failed: %s", err)
        except Exception as err:  # pragma: no cover - defensive safety path
            final_status = ControllerStatus.ERROR
            final_reason = "irrigation_cycle_failed"
            final_result = "failed"
            final_error = str(err)
            _LOGGER.exception("Unexpected irrigation cycle failure")
        finally:
            actuator_confirmed_off = not (
                self._pulse_active or self._actual_entity_is_active()
            )
            if not actuator_confirmed_off:
                try:
                    await self._async_turn_off_and_confirm()
                    stopped_at = dt_util.utcnow()
                    delivered = self._active_pulse_elapsed_seconds(stopped_at)
                    if delivered:
                        async with self._lock:
                            self._account_delivery(delivered, stopped_at)
                            delivered_event_seconds += delivered
                    actuator_confirmed_off = True
                except HomeAssistantError as err:
                    final_status = ControllerStatus.ERROR
                    final_reason = "irrigation_stop_failed"
                    final_result = "failed"
                    final_error = str(err)

            async with self._lock:
                self._cycle_task = None
                self._stop_event = None
                self._stop_reason = None
                self._stop_error = None
                self._entity_already_inactive = False
                self.state.status = final_status
                self.state.last_execution = dt_util.utcnow()
                self.state.next_pulse_at = None
                self.state.cycle_remaining_seconds = 0
                self.state.last_duration_seconds = delivered_event_seconds
                self.state.last_result = final_result
                self.state.last_skip_reason = (
                    final_reason
                    if final_result in {"skipped", "partial", "stopped"}
                    else None
                )
                self.state.last_error = final_error
                self.state.decision_reason = final_reason
                if actuator_confirmed_off:
                    self._clear_active_cycle_state()
                else:
                    # The entity may still be delivering water. Retain the pulse
                    # start and requested duration so a later stop or restart can
                    # account it, and keep ``is_irrigating`` true despite ERROR.
                    self._pulse_active = True
                await self._async_save()

    async def _async_execute_pulse(self, pulse_seconds: int) -> tuple[int, bool]:
        """Run one confirmed actuator pulse and return actual delivery seconds."""
        if self._stop_requested:
            return 0, True

        try:
            await self._async_turn_on_and_confirm()
        except HomeAssistantError:
            with suppress(HomeAssistantError):
                await self._async_turn_off_and_confirm()
            raise

        if self._stop_requested:
            with suppress(HomeAssistantError):
                await self._async_turn_off_and_confirm()
            return 0, True

        started = dt_util.utcnow()
        remained_active = True
        async with self._lock:
            # The entity may have turned off between the confirmation event and
            # this task regaining the transition lock. Recheck synchronously
            # before declaring the controller to be irrigating; once
            # ``_pulse_active`` is set, the permanent entity listener owns later
            # external-off reconciliation.
            remained_active = self._entity_matches_requested_state(active=True)
            if remained_active:
                self._pulse_active = True
                self.state.status = ControllerStatus.IRRIGATING
                self.state.active_started_at = started
                self.state.active_end_at = started + timedelta(seconds=pulse_seconds)
                self.state.next_pulse_at = None
                self.state.current_pulse_requested_seconds = pulse_seconds
                self.state.pulse_count_today += 1
                self.state.last_error = None
                self.state.decision_reason = "irrigation_pulse_running"
                await self._async_save()

        if not remained_active:
            with suppress(HomeAssistantError):
                await self._async_turn_off_and_confirm()
            raise HomeAssistantError(
                f"Irrigation entity {self.entity_id} did not remain active"
            )

        stopped_early = await self._async_wait_for_stop(pulse_seconds)

        if not self._entity_already_inactive:
            async with self._lock:
                self.state.decision_reason = "stopping_irrigation_pulse"
                await self._async_save()
            # Keep IRRIGATING and ``_pulse_active`` until the physical entity is
            # confirmed inactive. This prevents the UI from reporting Soaking while
            # the pump is still stopping and includes stop latency in accounting.
            await self._async_turn_off_and_confirm()

        stopped_at = dt_util.utcnow()
        delivered_seconds = self._active_pulse_elapsed_seconds(stopped_at)
        async with self._lock:
            self._account_delivery(delivered_seconds, stopped_at)
            self._pulse_active = False
            self.state.status = ControllerStatus.SOAKING
            self.state.decision_reason = "irrigation_pulse_completed"
            self.state.active_started_at = None
            self.state.active_end_at = None
            self.state.current_pulse_requested_seconds = 0
            await self._async_save()

        return delivered_seconds, stopped_early

    @property
    def _stop_requested(self) -> bool:
        """Return whether the active event has received a stop request."""
        return self._stop_event is not None and self._stop_event.is_set()

    async def _async_wait_for_stop(self, timeout_seconds: int) -> bool:
        """Wait for a stop request or timeout and return whether stop was requested."""
        stop_event = self._stop_event
        if stop_event is None:
            return False
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(0, timeout_seconds))
        except TimeoutError:
            return False
        return True

    def _requested_stop_outcome(
        self,
    ) -> tuple[ControllerStatus, str, str, str | None]:
        """Translate the active stop request into a final observable outcome."""
        reason = self._stop_reason or "manual_stop"
        error = self._stop_error
        if error:
            return ControllerStatus.ERROR, reason, "failed", error
        if reason == "rain_threshold_reached":
            return ControllerStatus.RAIN_PAUSED, reason, "partial", None
        if reason == "watering_window_closed":
            return ControllerStatus.SLEEPING, reason, "partial", None
        return ControllerStatus.MONITORING, reason, "stopped", None

    async def _async_automatic_continuation_outcome(
        self,
        remaining_seconds: int,
        *,
        ignore_rain: bool,
    ) -> tuple[int, ControllerStatus | None, str, str, str | None]:
        """Refresh and limit an automatic event before each new pulse.

        The scheduler does not start another event while this one is running or
        soaking. Refreshing here preserves the 15-minute responsiveness for long
        events and ensures a reduced forecast, new rain value, or consumed daily
        budget can stop later pulses safely.
        """
        if not self._automatic_window_open():
            return (
                0,
                ControllerStatus.SLEEPING,
                "watering_window_closed",
                "partial",
                None,
            )

        coordinator = self.entry.runtime_data.coordinator
        await coordinator.async_request_refresh()
        if not coordinator.last_update_success or coordinator.data is None:
            error = coordinator.last_exception
            return (
                0,
                ControllerStatus.ERROR,
                "source_data_unavailable",
                "failed",
                f"Source data unavailable: {error or 'refresh failed'}",
            )

        data = coordinator.data
        if (
            not ignore_rain
            and data.rain_mm is not None
            and data.rain_factor <= 0
        ):
            return (
                0,
                ControllerStatus.RAIN_PAUSED,
                "rain_threshold_reached",
                "partial",
                None,
            )

        available_seconds = max(
            0,
            self._available_budget_seconds(ignore_rain=ignore_rain)
            - self.delivered_today_seconds(),
        )
        if available_seconds <= 0:
            return (
                0,
                ControllerStatus.DAILY_BUDGET_REACHED,
                "daily_budget_exhausted",
                "completed",
                None,
            )
        return min(remaining_seconds, available_seconds), None, "", "", None

    def _available_budget_seconds(self, *, ignore_rain: bool) -> int:
        """Return today's calculated budget with optional rain removal."""
        data = self.entry.runtime_data.coordinator.data
        if data is None:
            return 0
        if not ignore_rain:
            return data.runtime_seconds
        peak_minutes = float(
            entry_value(self.entry, CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME)
        )
        return round(data.solar_factor * peak_minutes * MINUTES_TO_SECONDS)

    def _automatic_window_open(self) -> bool:
        """Return whether another automatic pulse may start at the current time."""
        return is_within_watering_window(
            self.entry,
            dt_util.now().time().replace(tzinfo=None),
        )

    @property
    def _max_pulse_seconds(self) -> int:
        """Return the configured maximum continuous pump-on duration in seconds."""
        minutes = float(
            entry_value(
                self.entry,
                CONF_MAX_PULSE_DURATION,
                DEFAULT_MAX_PULSE_DURATION,
            )
        )
        minutes = max(MIN_MAX_PULSE_DURATION, min(MAX_MAX_PULSE_DURATION, minutes))
        minutes = max(MIN_SOAK_DURATION, min(MAX_SOAK_DURATION, minutes))
        return max(1, round(minutes * MINUTES_TO_SECONDS))

    @property
    def _soak_seconds(self) -> int:
        """Return the configured pump-off soak interval in seconds."""
        minutes = float(
            entry_value(self.entry, CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION)
        )
        return max(1, round(minutes * MINUTES_TO_SECONDS))

    async def async_record_skip(self, reason: str) -> None:
        """Record a skipped event without operating the irrigation actuator."""
        async with self._lock:
            await self._record_skip_locked(reason)

    async def _record_skip_locked(self, reason: str) -> None:
        """Record a skipped event while the controller transition lock is held."""
        now = dt_util.utcnow()
        self.state.status = (
            ControllerStatus.RAIN_PAUSED
            if reason == "rain_threshold_reached"
            else ControllerStatus.MONITORING
        )
        self.state.last_execution = now
        self.state.last_skip_reason = reason
        self.state.last_duration_seconds = 0
        self.state.last_result = "skipped"
        self.state.decision_reason = reason
        self.state.last_error = None
        await self._async_save()

    async def async_prepare_for_evaluation(self) -> None:
        """Reset daily accounting when needed before an automatic evaluation."""
        async with self._lock:
            if self._reset_daily_delivery_if_needed():
                self.state.decision_reason = "new_day_budget_reset"
                await self._async_save()

    async def async_set_status(
        self,
        status: ControllerStatus,
        *,
        decision_reason: str | None = None,
        clear_error: bool = False,
        error_message: str | None = None,
    ) -> None:
        """Persist a scheduler-owned status without overwriting active execution.

        Source-data errors are sticky until a successful source refresh passes
        ``clear_error=True``. Actuator errors remain visible until a later manual
        or automatic event successfully starts, because a healthy sensor refresh
        does not prove that the physical actuator has recovered.
        """
        async with self._lock:
            if self.is_running or self.is_irrigating:
                return

            if status is ControllerStatus.ERROR:
                if (
                    self.state.status is ControllerStatus.ERROR
                    and self.state.decision_reason not in _RECOVERABLE_SOURCE_ERRORS
                    and decision_reason in _RECOVERABLE_SOURCE_ERRORS
                ):
                    # A source outage must not hide a more serious actuator or
                    # safety error that has not yet been proven recovered.
                    return
                if (
                    self.state.status is status
                    and self.state.decision_reason == decision_reason
                    and self.state.last_error == error_message
                ):
                    return
                self.state.status = status
                self.state.decision_reason = decision_reason
                self.state.last_error = error_message or self.state.last_error or (
                    decision_reason.replace("_", " ") if decision_reason else "Error"
                )
                await self._async_save()
                return

            if self.state.status is ControllerStatus.ERROR:
                if not clear_error:
                    return
                if self.state.decision_reason not in _RECOVERABLE_SOURCE_ERRORS:
                    return

            if (
                self.state.status is status
                and self.state.decision_reason == decision_reason
                and (not clear_error or self.state.last_error is None)
            ):
                return
            self.state.status = status
            self.state.decision_reason = decision_reason
            if clear_error:
                self.state.last_error = None
            await self._async_save()

    async def async_shutdown(self) -> None:
        """Stop active watering, remove listeners, and leave the actuator off."""
        await self.async_stop("integration_unloaded")
        if self._actual_entity_is_active():
            try:
                await self._async_turn_off_and_confirm()
            except HomeAssistantError:
                _LOGGER.exception(
                    "Irrigation entity %s remained active during shutdown",
                    self.entity_id,
                )
        if self._remove_entity_listener is not None:
            self._remove_entity_listener()
            self._remove_entity_listener = None
        self._listeners.clear()

    async def _async_turn_on_and_confirm(self) -> None:
        """Turn on the configured actuator and confirm its active state.

        The command-in-progress flag lets the permanent state listener distinguish
        the controller's own start transition from an unexpected external start
        during a soak interval.
        """
        domain = self.entity_id.split(".", 1)[0]
        service = "open_valve" if domain == "valve" else "turn_on"
        self._activation_in_progress = True
        try:
            try:
                await self.hass.services.async_call(
                    domain,
                    service,
                    {"entity_id": self.entity_id},
                    blocking=True,
                )
            except Exception as err:
                raise HomeAssistantError(
                    f"Failed to start irrigation entity {self.entity_id}: {err}"
                ) from err
            await self._async_wait_for_entity_state(active=True)
        finally:
            self._activation_in_progress = False

    async def _async_turn_off_and_confirm(self) -> None:
        """Turn off the configured actuator and confirm its inactive state.

        Valve integrations can report an intermediate ``closing`` state. The
        command-in-progress flag prevents that expected transition from being
        mistaken for an external start during a soak interval. An already
        confirmed inactive entity needs no redundant service call.
        """
        if self._entity_matches_requested_state(active=False):
            return
        domain = self.entity_id.split(".", 1)[0]
        service = "close_valve" if domain == "valve" else "turn_off"
        self._deactivation_in_progress = True
        try:
            try:
                await self.hass.services.async_call(
                    domain,
                    service,
                    {"entity_id": self.entity_id},
                    blocking=True,
                )
            except Exception as err:
                raise HomeAssistantError(
                    f"Failed to stop irrigation entity {self.entity_id}: {err}"
                ) from err
            await self._async_wait_for_entity_state(active=False)
        finally:
            self._deactivation_in_progress = False

    async def _async_wait_for_entity_state(self, *, active: bool) -> None:
        """Wait briefly for the actuator to report the commanded state."""
        if self._entity_matches_requested_state(active=active):
            return

        state_changed = asyncio.Event()

        @callback
        def handle_state_change(event: Event[EventStateChangedData]) -> None:
            """Wake the confirmation waiter when the requested state appears."""
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            is_active = self._entity_state_is_active(new_state.state)
            is_confirmed_inactive = (
                new_state.state not in {STATE_UNKNOWN, STATE_UNAVAILABLE}
                and not is_active
            )
            if (active and is_active) or (not active and is_confirmed_inactive):
                state_changed.set()

        remove_listener = async_track_state_change_event(
            self.hass,
            [self.entity_id],
            handle_state_change,
        )
        try:
            if self._entity_matches_requested_state(active=active):
                return
            try:
                await asyncio.wait_for(
                    state_changed.wait(),
                    timeout=ACTUATOR_CONFIRM_TIMEOUT_SECONDS,
                )
            except TimeoutError as err:
                expected = "active" if active else "inactive"
                current = self.hass.states.get(self.entity_id)
                current_state = current.state if current else "missing"
                raise HomeAssistantError(
                    f"Irrigation entity {self.entity_id} did not become {expected}; "
                    f"current state is {current_state}"
                ) from err
        finally:
            remove_listener()

    def _entity_matches_requested_state(self, *, active: bool) -> bool:
        """Return whether the current actuator state confirms the command."""
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return False
        is_active = self._entity_state_is_active(state.state)
        if active:
            return is_active
        return state.state not in {STATE_UNKNOWN, STATE_UNAVAILABLE} and not is_active

    def delivered_today_seconds(self) -> int:
        """Return accumulated pump-on runtime for the current local day."""
        today = dt_util.now().date().isoformat()
        if self.state.delivery_date != today:
            return 0
        return self.state.delivered_today_seconds

    def pulse_count_today(self) -> int:
        """Return the number of confirmed pump-on pulses for the local day."""
        today = dt_util.now().date().isoformat()
        if self.state.delivery_date != today:
            return 0
        return self.state.pulse_count_today

    def _reset_daily_delivery_if_needed(
        self,
        timestamp: datetime | None = None,
    ) -> bool:
        """Reset delivered-water counters when the local calendar day changes."""
        timestamp = timestamp or dt_util.utcnow()
        local_date = dt_util.as_local(timestamp).date().isoformat()
        if self.state.delivery_date == local_date:
            return False
        self.state.delivery_date = local_date
        self.state.delivered_today_seconds = 0
        self.state.pulse_count_today = 0
        return True

    def _account_delivery(self, delivered_seconds: int, timestamp: datetime) -> None:
        """Add measured pump-on time to the current local-day counter."""
        self._reset_daily_delivery_if_needed(timestamp)
        self.state.delivered_today_seconds += max(0, delivered_seconds)

    def _active_pulse_elapsed_seconds(self, stopped_at: datetime) -> int:
        """Return measured pump-on time through confirmed physical stop.

        Actual delivery can exceed the requested pulse by actuator stop latency.
        Counting that extra time keeps the daily budget conservative and makes the
        requested-versus-actual observability fields truthful.
        """
        started_at = self.state.active_started_at
        if started_at is None:
            return 0
        return max(0, round((stopped_at - started_at).total_seconds()))

    def _recover_active_pulse_seconds(
        self,
        recovered_at: datetime,
        *,
        conservatively_assume_active: bool = False,
    ) -> int:
        """Estimate delivered seconds for a pulse interrupted by restart.

        When the actuator is still active, or a persisted stop failure left the
        physical off time unknown, delivery is conservatively counted through the
        confirmed recovery time even when that exceeds the requested pulse. When
        the actuator is already inactive, the planned pulse end remains the safest
        available upper bound because the exact earlier off time is unavailable.
        """
        started_at = self.state.active_started_at
        if started_at is None:
            return 0
        effective_end = recovered_at
        if not conservatively_assume_active and self.state.active_end_at is not None:
            effective_end = min(effective_end, self.state.active_end_at)
        elapsed = max(0, round((effective_end - started_at).total_seconds()))
        if conservatively_assume_active:
            return elapsed
        requested = self.state.current_pulse_requested_seconds
        return min(elapsed, requested) if requested > 0 else elapsed

    def _clear_active_cycle_state(self) -> None:
        """Clear transient pulse and soak fields after an event ends."""
        self._pulse_active = False
        self._activation_in_progress = False
        self._deactivation_in_progress = False
        self.state.active_started_at = None
        self.state.active_end_at = None
        self.state.next_pulse_at = None
        self.state.current_pulse_requested_seconds = 0
        self.state.cycle_remaining_seconds = 0

    async def _async_save(self) -> None:
        """Persist state and immediately notify controller-backed entities."""
        try:
            await self._store.async_save(self.state.as_dict())
        finally:
            self._notify_listeners()
