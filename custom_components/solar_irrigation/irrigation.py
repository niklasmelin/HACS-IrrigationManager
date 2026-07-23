"""Safe irrigation execution and persistence support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_IRRIGATION_ENTITY,
    ControllerStatus,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .models import (
    SolarIrrigationConfigEntry,
    SolarIrrigationControllerState,
)

_LOGGER = logging.getLogger(__name__)


class SolarIrrigationController:
    """Control one irrigation entity without overlapping execution."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SolarIrrigationConfigEntry,
    ) -> None:
        """Initialize controller state, locking, and entry-specific storage."""
        self.hass = hass
        self.entry = entry
        self.state = SolarIrrigationControllerState()
        self._lock = asyncio.Lock()
        self._run_task: asyncio.Task[None] | None = None
        self._remove_entity_listener: Callable[[], None] | None = None
        self._stopping = False
        self._store: Store[dict[str, object]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id),
        )

    @property
    def entity_id(self) -> str:
        """Return the configured irrigation entity ID."""
        return str(
            self.entry.options.get(
                CONF_IRRIGATION_ENTITY,
                self.entry.data[CONF_IRRIGATION_ENTITY],
            )
        )

    @property
    def is_running(self) -> bool:
        """Return whether an irrigation run is currently active."""
        return self._run_task is not None and not self._run_task.done()

    async def async_load(self) -> None:
        """Load persisted controller state and enforce a safe restart state."""
        stored = await self._store.async_load()
        if stored:
            self.state = SolarIrrigationControllerState.from_dict(stored)
        self._reset_daily_delivery_if_needed()
        if self.state.status is ControllerStatus.IRRIGATING:
            await self._async_turn_off()
            self.state.status = ControllerStatus.MONITORING
            self.state.active_started_at = None
            self.state.active_end_at = None
            self.state.last_error = "Recovered from an interrupted irrigation run"
            await self._async_save()
        elif self.state.status is ControllerStatus.INITIALIZING:
            self.state.status = ControllerStatus.MONITORING
            await self._async_save()

    async def async_start_monitoring(self) -> None:
        """Subscribe to irrigation-entity state changes.

        The controller timer represents the intended run, while the configured
        switch or valve represents the actual irrigation state. External
        automations, manual operation, device protections, or integration
        failures can turn the entity off before the timer ends. This listener
        reconciles persistent controller state with the physical entity so the
        status cannot remain ``irrigating`` after watering has stopped.
        """
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
        """Reconcile a changed pump or valve state with controller state.

        State changes caused by the controller's own stop sequence are ignored
        because that sequence performs its own accounting and persistence. An
        unexpected inactive state ends the active run without issuing another
        turn-off service call. Unknown or unavailable states terminate the run
        and expose an error because actual water delivery can no longer be
        confirmed.
        """
        if self._stopping:
            return
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        expected_active = (
            self.is_running or self.state.status is ControllerStatus.IRRIGATING
        )
        if not expected_active:
            return
        if new_state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
            await self._async_reconcile_external_stop(
                reason="irrigation_entity_unavailable",
                error=f"Irrigation entity became {new_state.state}",
            )
            return
        if not self._entity_state_is_active(new_state.state):
            await self._async_reconcile_external_stop(
                reason="irrigation_entity_turned_off",
            )

    def _entity_state_is_active(self, state: str) -> bool:
        """Return whether an entity state means that irrigation is active."""
        domain = self.entity_id.split(".", 1)[0]
        if domain == "valve":
            return state in {"open", "opening"}
        return state == STATE_ON

    async def _async_reconcile_external_stop(
        self,
        *,
        reason: str,
        error: str | None = None,
    ) -> None:
        """Finish accounting after the irrigation entity stops externally.

        This method deliberately does not call the entity's turn-off service:
        the observed state already confirms that watering is inactive. It
        cancels the internal duration timer, records the elapsed delivery, and
        updates the visible status to monitoring or error.
        """
        async with self._lock:
            if not (
                self.is_running
                or self.state.status is ControllerStatus.IRRIGATING
            ):
                return
            task = self._run_task
            self._run_task = None
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
            stopped_at = dt_util.utcnow()
            delivered_seconds = 0
            if self.state.active_started_at is not None:
                delivered_seconds = max(
                    0,
                    round(
                        (stopped_at - self.state.active_started_at).total_seconds()
                    ),
                )
            self._reset_daily_delivery_if_needed(stopped_at)
            self.state.delivered_today_seconds += delivered_seconds
            self.state.status = (
                ControllerStatus.ERROR if error else ControllerStatus.MONITORING
            )
            self.state.last_execution = stopped_at
            self.state.active_started_at = None
            self.state.active_end_at = None
            self.state.last_skip_reason = reason
            self.state.decision_reason = reason
            self.state.last_error = error
            await self._async_save()

    async def async_run(
        self,
        duration_minutes: float | None = None,
        *,
        automatic: bool = False,
        ignore_rain: bool = False,
    ) -> bool:
        """Start irrigation and schedule a safe stop after the selected duration."""
        async with self._lock:
            self._reset_daily_delivery_if_needed()
            if self.is_running:
                raise HomeAssistantError("Irrigation is already running")
            data = self.entry.runtime_data.coordinator.data
            if data is None:
                raise HomeAssistantError("Irrigation calculation data is unavailable")
            if data.rain_mm is not None and data.rain_factor <= 0 and not ignore_rain:
                await self.async_record_skip(
                    data.skip_reason or "rain_threshold_reached",
                    automatic=automatic,
                )
                return False
            duration_seconds = (
                round(float(duration_minutes) * 60)
                if duration_minutes is not None
                else data.runtime_seconds
            )
            if duration_seconds <= 0:
                await self.async_record_skip(
                    data.skip_reason or "zero_runtime",
                    automatic=automatic,
                )
                return False
            await self._async_turn_on()
            started = dt_util.utcnow()
            self.state.status = ControllerStatus.IRRIGATING
            self.state.active_started_at = started
            self.state.active_end_at = started + timedelta(seconds=duration_seconds)
            self.state.last_duration_seconds = duration_seconds
            self.state.last_error = None
            self.state.decision_reason = "irrigation_started"
            self.state.pulse_count_today += 1
            if automatic:
                self.state.last_automatic_date = dt_util.as_local(started).date().isoformat()
            await self._async_save()
            self._run_task = self.hass.async_create_task(
                self._async_complete_after(duration_seconds),
                "solar_irrigation_run",
            )
            return True

    async def async_stop(self, reason: str = "manual_stop") -> None:
        """Stop any active run, turn off the valve, and persist final state."""
        task = self._run_task
        self._run_task = None
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
        stopped_at = dt_util.utcnow()
        delivered_seconds = 0
        if self.state.active_started_at is not None:
            delivered_seconds = max(
                0,
                round((stopped_at - self.state.active_started_at).total_seconds()),
            )
        self._stopping = True
        try:
            await self._async_turn_off()
        finally:
            self._stopping = False
            self._reset_daily_delivery_if_needed(stopped_at)
            self.state.delivered_today_seconds += delivered_seconds
            self.state.status = ControllerStatus.MONITORING
            self.state.last_execution = stopped_at
            self.state.active_started_at = None
            self.state.active_end_at = None
            self.state.last_skip_reason = reason if reason != "completed" else None
            self.state.decision_reason = (
                "run_completed" if reason == "completed" else reason
            )
            await self._async_save()

    async def async_record_skip(self, reason: str, *, automatic: bool) -> None:
        """Record a safe skipped run without operating the irrigation entity."""
        now = dt_util.utcnow()
        self.state.status = ControllerStatus.MONITORING
        self.state.last_execution = now
        self.state.last_skip_reason = reason
        self.state.last_duration_seconds = 0
        self.state.decision_reason = reason
        if automatic:
            self.state.last_automatic_date = dt_util.as_local(now).date().isoformat()
        await self._async_save()

    def automatic_decision_made_today(self) -> bool:
        """Return whether today's scheduled automatic decision is already stored."""
        return self.state.last_automatic_date == dt_util.now().date().isoformat()


    async def async_set_status(
        self,
        status: ControllerStatus,
        *,
        decision_reason: str | None = None,
    ) -> None:
        """Persist an externally determined controller status when it changes.

        Scheduling owns states such as ``sleeping`` and ``monitoring`` while the
        controller owns execution states such as ``irrigating`` and ``error``.
        This method provides a small, serialized boundary between those parts
        and avoids unnecessary storage writes when neither visible value changed.
        Active irrigation is never overwritten by a background scheduler tick.
        """
        async with self._lock:
            if self.is_running or self.state.status is ControllerStatus.IRRIGATING:
                return
            if (
                self.state.status is status
                and self.state.decision_reason == decision_reason
            ):
                return
            self.state.status = status
            self.state.decision_reason = decision_reason
            await self._async_save()

    async def async_shutdown(self) -> None:
        """Remove listeners, cancel timers, and leave irrigation safely off."""
        if self._remove_entity_listener is not None:
            self._remove_entity_listener()
            self._remove_entity_listener = None
        if self.is_running or self.state.status is ControllerStatus.IRRIGATING:
            await self.async_stop("integration_unloaded")

    async def _async_complete_after(self, duration_seconds: int) -> None:
        """Wait for the run duration and then complete irrigation safely."""
        try:
            await asyncio.sleep(duration_seconds)
            await self.async_stop("completed")
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - defensive safety path
            _LOGGER.exception("Unexpected irrigation timer failure")
            self.state.status = ControllerStatus.ERROR
            self.state.last_error = str(err)
            await self._async_turn_off()
            await self._async_save()

    async def _async_turn_on(self) -> None:
        """Call the configured entity domain's turn-on service."""
        domain = self.entity_id.split(".", 1)[0]
        service = "open_valve" if domain == "valve" else "turn_on"
        await self.hass.services.async_call(
            domain,
            service,
            {"entity_id": self.entity_id},
            blocking=True,
        )

    async def _async_turn_off(self) -> None:
        """Call the configured entity domain's turn-off service."""
        domain = self.entity_id.split(".", 1)[0]
        service = "close_valve" if domain == "valve" else "turn_off"
        await self.hass.services.async_call(
            domain,
            service,
            {"entity_id": self.entity_id},
            blocking=True,
        )

    def delivered_today_seconds(self) -> int:
        """Return today's delivered runtime without mutating persisted state."""
        today = dt_util.now().date().isoformat()
        if self.state.delivery_date != today:
            return 0
        return self.state.delivered_today_seconds

    def pulse_count_today(self) -> int:
        """Return today's pulse count without mutating persisted state."""
        today = dt_util.now().date().isoformat()
        if self.state.delivery_date != today:
            return 0
        return self.state.pulse_count_today

    def _reset_daily_delivery_if_needed(self, timestamp=None) -> None:
        """Reset delivered-water counters when the local calendar day changes."""
        timestamp = timestamp or dt_util.utcnow()
        local_date = dt_util.as_local(timestamp).date().isoformat()
        if self.state.delivery_date == local_date:
            return
        self.state.delivery_date = local_date
        self.state.delivered_today_seconds = 0
        self.state.pulse_count_today = 0

    async def _async_save(self) -> None:
        """Persist current controller state for restart recovery."""
        await self._store.async_save(self.state.as_dict())
