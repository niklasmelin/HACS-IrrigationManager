"""Set up Solar Irrigation actions, entries, and automatic evaluation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    AUTOMATIC_EVALUATION_INTERVAL_SECONDS,
    CONF_DURATION,
    CONF_ENTRY_ID,
    CONF_IGNORE_RAIN,
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    CONF_SCHEDULE_TIME,
    CONF_SOAK_DURATION,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_SOAK_DURATION,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
    DOMAIN,
    MAX_MAX_PULSE_DURATION,
    MAX_MAX_RUNTIME,
    MAX_SOAK_DURATION,
    MIN_AUTOMATIC_EVENT_SECONDS,
    MIN_MAX_PULSE_DURATION,
    MIN_MAX_RUNTIME,
    MIN_SOAK_DURATION,
    PLATFORMS,
    SVC_RUN_NOW,
    SVC_STOP,
    ControllerStatus,
)
from .coordinator import SolarIrrigationCoordinator
from .irrigation import SolarIrrigationController
from .models import SolarIrrigationConfigEntry, SolarIrrigationRuntimeData
from .watering_window import delivery_progress, is_within_watering_window

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _validate_service_entry_target(data: dict[str, Any]) -> dict[str, Any]:
    """Require exactly one current or legacy config-entry identifier."""
    current = data.get(ATTR_CONFIG_ENTRY_ID)
    legacy = data.get(CONF_ENTRY_ID)
    if bool(current) == bool(legacy):
        raise vol.Invalid(
            f"Provide exactly one of {ATTR_CONFIG_ENTRY_ID!r} or {CONF_ENTRY_ID!r}"
        )
    return data


def _service_schema(extra: dict[Any, Any] | None = None) -> vol.Schema:
    """Build a backward-compatible config-entry-targeted action schema."""
    fields: dict[Any, Any] = {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_ENTRY_ID): cv.string,
    }
    if extra:
        fields.update(extra)
    return vol.All(vol.Schema(fields), _validate_service_entry_target)


RUN_NOW_SCHEMA = _service_schema(
    {
        vol.Optional(CONF_DURATION): vol.All(
            vol.Coerce(float),
            vol.Range(min=0.01, max=1440),
        ),
        vol.Optional(CONF_IGNORE_RAIN, default=False): cv.boolean,
    }
)
STOP_SCHEMA = _service_schema()


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration actions once, independently of loaded entries."""
    del config

    async def async_run_now(call: ServiceCall) -> None:
        """Start a manual pulse-and-soak event for one config entry."""
        entry = _get_loaded_entry(hass, _service_entry_id(call))
        duration = call.data.get(CONF_DURATION)
        ignore_rain = call.data[CONF_IGNORE_RAIN]
        coordinator = entry.runtime_data.coordinator

        # Calculated duration and rain protection require fresh source data. An
        # explicit duration combined with ignore_rain is a deliberate operator
        # override and remains usable when a source sensor is temporarily down.
        await coordinator.async_request_refresh()
        if not coordinator.last_update_success and not ignore_rain:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="source_data_unavailable",
            )

        await entry.runtime_data.controller.async_run(
            duration,
            automatic=False,
            ignore_rain=ignore_rain,
        )

    async def async_stop(call: ServiceCall) -> None:
        """Stop the active event for one config entry."""
        entry = _get_loaded_entry(hass, _service_entry_id(call))
        await entry.runtime_data.controller.async_stop("manual_stop")

    if not hass.services.has_service(DOMAIN, SVC_RUN_NOW):
        hass.services.async_register(
            DOMAIN,
            SVC_RUN_NOW,
            async_run_now,
            schema=RUN_NOW_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SVC_STOP):
        hass.services.async_register(
            DOMAIN,
            SVC_STOP,
            async_stop,
            schema=STOP_SCHEMA,
        )
    return True


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Migrate legacy scheduling and normalize delivery settings safely.

    Version 2 replaced the single daily trigger with a watering window. Version 3
    introduces pulse-and-soak defaults and guarantees that an older peak daily
    water-demand value is valid for the writable 10-240 minute number entity.
    """
    if entry.version >= 3:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    if entry.version < 2:
        legacy_start = str(
            options.pop(
                CONF_SCHEDULE_TIME,
                data.pop(CONF_SCHEDULE_TIME, DEFAULT_WATERING_WINDOW_START),
            )
        )
        options.setdefault(CONF_WATERING_WINDOW_START, legacy_start)
        options.setdefault(CONF_WATERING_WINDOW_END, DEFAULT_WATERING_WINDOW_END)

    raw_demand = options.get(
        CONF_MAX_RUNTIME,
        data.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
    )
    try:
        peak_demand = float(raw_demand)
    except (TypeError, ValueError):
        peak_demand = DEFAULT_MAX_RUNTIME
    options[CONF_MAX_RUNTIME] = max(
        MIN_MAX_PULSE_DURATION,
    MIN_MAX_RUNTIME,
    MIN_SOAK_DURATION,
        min(MAX_MAX_RUNTIME, peak_demand),
    )
    raw_pulse = options.get(
        CONF_MAX_PULSE_DURATION,
        data.get(CONF_MAX_PULSE_DURATION, DEFAULT_MAX_PULSE_DURATION),
    )
    try:
        max_pulse_duration = float(raw_pulse)
    except (TypeError, ValueError):
        max_pulse_duration = DEFAULT_MAX_PULSE_DURATION
    options[CONF_MAX_PULSE_DURATION] = max(
        MIN_MAX_PULSE_DURATION,
        min(MAX_MAX_PULSE_DURATION, max_pulse_duration),
    )

    raw_soak = options.get(
        CONF_SOAK_DURATION,
        data.get(CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION),
    )
    try:
        soak_duration = float(raw_soak)
    except (TypeError, ValueError):
        soak_duration = DEFAULT_SOAK_DURATION
    options[CONF_SOAK_DURATION] = max(
        MIN_SOAK_DURATION,
        min(MAX_SOAK_DURATION, soak_duration),
    )

    irrigation_entity = str(
        options.get(
            CONF_IRRIGATION_ENTITY,
            data.get(CONF_IRRIGATION_ENTITY, ""),
        )
    )
    if irrigation_entity:
        for other_entry in hass.config_entries.async_entries(DOMAIN):
            if other_entry.entry_id == entry.entry_id:
                continue
            other_entity = str(
                other_entry.options.get(
                    CONF_IRRIGATION_ENTITY,
                    other_entry.data.get(CONF_IRRIGATION_ENTITY, ""),
                )
            )
            if other_entity == irrigation_entity:
                _LOGGER.error(
                    "Cannot migrate Solar Irrigation entry %s because %s is "
                    "already controlled by entry %s",
                    entry.entry_id,
                    irrigation_entity,
                    other_entry.entry_id,
                )
                return False

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        unique_id=irrigation_entity or entry.unique_id,
        version=4,
    )
    _LOGGER.info(
        "Migrated Solar Irrigation entry %s to schema version 4",
        entry.entry_id,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Create runtime objects, platforms, listeners, and periodic evaluation.

    Controller recovery and monitoring start before the first source refresh so
    a temporary sensor outage cannot bypass physical actuator safety. Every
    partially completed setup path removes the
    listener and leaves the actuator safely off. Entry-owned synchronous
    callbacks are also registered with ``async_on_unload`` as a lifecycle safety
    net.
    """
    coordinator = SolarIrrigationCoordinator(hass, entry)
    controller = SolarIrrigationController(hass, entry)
    entry.runtime_data = SolarIrrigationRuntimeData(
        coordinator=coordinator,
        controller=controller,
    )

    platforms_loaded = False
    try:
        # Restore and secure the physical actuator before a source refresh can
        # postpone entry setup. A temporary solar or rain outage must never leave
        # an actuator active merely because the coordinator raised ConfigEntryNotReady.
        await controller.async_load()
        await controller.async_start_monitoring()
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        platforms_loaded = True

        runtime = entry.runtime_data
        runtime.remove_update_listener = entry.add_update_listener(
            _async_reload_entry
        )
        runtime.cancel_schedule = _schedule_automatic_evaluation(hass, entry)
        entry.async_on_unload(lambda: _cancel_runtime_callbacks(entry))
    except Exception:
        _cancel_runtime_callbacks(entry)
        if platforms_loaded:
            await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        try:
            await controller.async_shutdown()
        except Exception:  # pragma: no cover - cleanup must not hide root cause
            _LOGGER.exception("Failed to clean up a partially set up controller")
        raise

    if controller.state.status is not ControllerStatus.ERROR:
        if is_within_watering_window(
            entry,
            dt_util.now().time().replace(tzinfo=None),
        ):
            await controller.async_set_status(
                ControllerStatus.MONITORING,
                decision_reason="automatic_window_open",
            )
        else:
            await controller.async_set_status(
                ControllerStatus.SLEEPING,
                decision_reason="outside_watering_window",
            )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Unload platforms before releasing callbacks and stopping the controller."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    _cancel_runtime_callbacks(entry)
    await entry.runtime_data.controller.async_shutdown()
    return True


@callback
def _cancel_runtime_callbacks(entry: SolarIrrigationConfigEntry) -> None:
    """Cancel entry-owned update and timer callbacks exactly once."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return
    if runtime.cancel_schedule:
        runtime.cancel_schedule()
        runtime.cancel_schedule = None
    if runtime.remove_update_listener:
        runtime.remove_update_listener()
        runtime.remove_update_listener = None


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> None:
    """Reload after options change unless an in-place number update requested it."""
    runtime = entry.runtime_data
    if runtime.suppress_next_reload:
        runtime.suppress_next_reload = False
        return
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_automatic_evaluation(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> Callable[[], None]:
    """Register the fixed 15-minute automatic irrigation evaluator."""

    async def async_evaluate(now: datetime) -> None:
        """Delegate a periodic timer event to the entry-specific evaluator."""
        await _async_evaluate_automatic_irrigation(hass, entry, now)

    return async_track_time_interval(
        hass,
        async_evaluate,
        timedelta(seconds=AUTOMATIC_EVALUATION_INTERVAL_SECONDS),
    )


async def _async_evaluate_automatic_irrigation(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    now: datetime,
) -> None:
    """Refresh inputs and start the amount of water due at this timer tick.

    The current daily budget is distributed across the configured watering
    window. Manual and prior automatic delivery are subtracted from both the
    target-to-date and the hard daily budget. A running or soaking event owns the
    actuator until complete, so this evaluator never creates overlapping cycles.
    """
    del hass
    controller = entry.runtime_data.controller
    coordinator = entry.runtime_data.coordinator
    local_now = dt_util.as_local(now)

    await controller.async_prepare_for_evaluation()

    if not is_within_watering_window(
        entry,
        local_now.time().replace(tzinfo=None),
    ):
        await controller.async_set_status(
            ControllerStatus.SLEEPING,
            decision_reason="outside_watering_window",
        )
        return

    if controller.is_running:
        return

    await coordinator.async_request_refresh()
    if not coordinator.last_update_success or coordinator.data is None:
        exception = coordinator.last_exception
        message = f"Source data unavailable: {exception or 'refresh failed'}"
        _LOGGER.warning("Automatic irrigation evaluation skipped: %s", message)
        await controller.async_set_status(
            ControllerStatus.ERROR,
            decision_reason="source_data_unavailable",
            error_message=message,
        )
        return

    data = coordinator.data
    delivered_seconds = controller.delivered_today_seconds()
    remaining_budget_seconds = max(0, data.runtime_seconds - delivered_seconds)

    if data.rain_mm is not None and data.rain_factor <= 0:
        await controller.async_set_status(
            ControllerStatus.RAIN_PAUSED,
            decision_reason="rain_threshold_reached",
            clear_error=True,
        )
        return

    if remaining_budget_seconds <= 0:
        await controller.async_set_status(
            ControllerStatus.DAILY_BUDGET_REACHED,
            decision_reason="daily_budget_exhausted",
            clear_error=True,
        )
        return

    progress = delivery_progress(entry, local_now)
    target_seconds = round(data.runtime_seconds * progress)
    due_seconds = min(
        remaining_budget_seconds,
        max(0, target_seconds - delivered_seconds),
    )

    if due_seconds < MIN_AUTOMATIC_EVENT_SECONDS:
        status = (
            ControllerStatus.WAITING_FOR_HISTORY
            if data.solar_sample_count == 0
            else ControllerStatus.WAITING_FOR_PULSE
        )
        reason = (
            "collecting_solar_history"
            if data.solar_sample_count == 0
            else "waiting_for_water_demand"
        )
        await controller.async_set_status(
            status,
            decision_reason=reason,
            clear_error=True,
        )
        return

    try:
        await controller.async_run(
            due_seconds / 60,
            automatic=True,
            ignore_rain=False,
        )
    except HomeAssistantError as err:
        _LOGGER.error("Automatic irrigation could not start: %s", err)
        await controller.async_set_status(
            ControllerStatus.ERROR,
            decision_reason="automatic_irrigation_start_failed",
            error_message=str(err),
        )


def _service_entry_id(call: ServiceCall) -> str:
    """Return the current or backward-compatible entry identifier."""
    return str(call.data.get(ATTR_CONFIG_ENTRY_ID) or call.data[CONF_ENTRY_ID])


def _get_loaded_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> SolarIrrigationConfigEntry:
    """Resolve a loaded entry or raise a translated validation error."""
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if (
        entry.state is not ConfigEntryState.LOADED
        or getattr(entry, "runtime_data", None) is None
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"entry_id": entry_id},
        )
    return cast(SolarIrrigationConfigEntry, entry)
