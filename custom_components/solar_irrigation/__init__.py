"""Set up Solar Irrigation services, config entries, and automatic evaluation."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    AUTOMATIC_EVALUATION_INTERVAL_SECONDS,
    CONF_DURATION,
    CONF_ENTRY_ID,
    CONF_IGNORE_RAIN,
    CONF_SCHEDULE_TIME,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
    DOMAIN,
    PLATFORMS,
    SVC_RUN_NOW,
    SVC_STOP,
    ControllerStatus,
)
from .coordinator import SolarIrrigationCoordinator
from .irrigation import SolarIrrigationController
from .models import SolarIrrigationConfigEntry, SolarIrrigationRuntimeData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
RUN_NOW_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTRY_ID): cv.string,
        vol.Optional(CONF_DURATION): vol.All(vol.Coerce(float), vol.Range(min=0)),
        vol.Optional(CONF_IGNORE_RAIN, default=False): cv.boolean,
    }
)
STOP_SCHEMA = vol.Schema({vol.Required(CONF_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register domain services once, independently of individual entries.

    The services resolve a loaded config entry by ID and delegate all pump or
    valve operation to its entry-owned controller. Keeping service registration
    at domain level avoids duplicate registrations when multiple irrigation
    circuits are configured.
    """
    del config

    async def async_run_now(call: ServiceCall) -> None:
        """Start a manual irrigation run for the requested config entry."""
        entry = _get_loaded_entry(hass, call.data[CONF_ENTRY_ID])
        await entry.runtime_data.controller.async_run(
            call.data.get(CONF_DURATION),
            automatic=False,
            ignore_rain=call.data[CONF_IGNORE_RAIN],
        )

    async def async_stop(call: ServiceCall) -> None:
        """Stop the active irrigation run for the requested config entry."""
        entry = _get_loaded_entry(hass, call.data[CONF_ENTRY_ID])
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
    """Migrate pre-2.3 scheduling data to an automatic watering window.

    Version 2.2 and earlier stored one ``schedule_time`` value. Version 2.3
    replaces that one-shot concept with a start and end time. The old daily
    irrigation time is preserved as the initial window start so an upgrade does
    not unexpectedly make irrigation begin earlier than before. The window end
    receives the safe default of 22:00.
    """
    if entry.version >= 2:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    legacy_start = str(
        options.pop(
            CONF_SCHEDULE_TIME,
            data.pop(CONF_SCHEDULE_TIME, DEFAULT_WATERING_WINDOW_START),
        )
    )
    options.setdefault(CONF_WATERING_WINDOW_START, legacy_start)
    options.setdefault(CONF_WATERING_WINDOW_END, DEFAULT_WATERING_WINDOW_END)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=2,
    )
    _LOGGER.info(
        "Migrated Solar Irrigation entry %s to watering window %s-%s",
        entry.entry_id,
        options[CONF_WATERING_WINDOW_START],
        options[CONF_WATERING_WINDOW_END],
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Create entry-owned runtime objects and start periodic evaluation.

    The coordinator loads and validates source data first. The controller then
    restores persistent delivery state and enforces a safe pump-off condition.
    Finally, entity platforms are forwarded and a 15-minute automatic evaluator
    is registered. The evaluator remains active overnight for state maintenance
    but cannot start automatic irrigation outside the configured window.
    """
    coordinator = SolarIrrigationCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    controller = SolarIrrigationController(hass, entry)
    runtime = SolarIrrigationRuntimeData(
        coordinator=coordinator,
        controller=controller,
    )
    entry.runtime_data = runtime
    await controller.async_load()

    runtime.remove_update_listener = entry.add_update_listener(_async_reload_entry)
    runtime.cancel_schedule = _schedule_automatic_evaluation(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Establish the correct visible state immediately without starting the pump
    # during integration setup. The first periodic tick performs evaluation.
    if _is_within_watering_window(entry, dt_util.now().time()):
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
    """Unload platforms and safely release entry-owned listeners and timers."""
    runtime = entry.runtime_data
    if runtime.cancel_schedule:
        runtime.cancel_schedule()
        runtime.cancel_schedule = None
    if runtime.remove_update_listener:
        runtime.remove_update_listener()
        runtime.remove_update_listener = None
    await runtime.controller.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> None:
    """Reload a config entry after an option or writable setting changes."""
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_automatic_evaluation(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
):
    """Evaluate automatic irrigation every 15 minutes.

    Version 2.3 intentionally changes scheduling from a single wall-clock event
    to periodic evaluation bounded by a watering window. The current controller
    still protects against more than one automatic decision per local day; the
    periodic structure is the foundation for later multi-pulse allocation and
    already provides meaningful sleeping/monitoring states.
    """

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
    """Refresh inputs and make a safe automatic decision when allowed.

    Outside the configured watering window the controller enters ``sleeping``
    and no automatic operation can start. Inside the window it enters
    ``monitoring``. For compatibility with the current daily-budget executor,
    only the first eligible evaluation of each local day starts or records an
    automatic decision. Manual service calls remain available at all times.
    """
    del hass
    controller = entry.runtime_data.controller
    local_now = dt_util.as_local(now)
    if not _is_within_watering_window(entry, local_now.time()):
        await controller.async_set_status(
            ControllerStatus.SLEEPING,
            decision_reason="outside_watering_window",
        )
        return

    if not controller.is_running:
        await controller.async_set_status(
            ControllerStatus.MONITORING,
            decision_reason="automatic_window_open",
        )

    if controller.automatic_decision_made_today() or controller.is_running:
        return

    await entry.runtime_data.coordinator.async_request_refresh()
    if not entry.runtime_data.coordinator.last_update_success:
        _LOGGER.warning(
            "Automatic irrigation evaluation skipped because source data is unavailable"
        )
        await controller.async_set_status(
            ControllerStatus.ERROR,
            decision_reason="source_data_unavailable",
        )
        return
    await controller.async_run(automatic=True)


def _is_within_watering_window(
    entry: SolarIrrigationConfigEntry,
    current_time: time,
) -> bool:
    """Return whether a local time lies inside the configured watering window.

    Normal windows such as 05:00-22:00 use an inclusive start and exclusive end.
    Overnight windows such as 22:00-05:00 are also supported by wrapping across
    midnight. Equal start and end values are rejected by the config flow, but
    are treated defensively as a closed window here.
    """
    start = _entry_time(
        entry,
        CONF_WATERING_WINDOW_START,
        DEFAULT_WATERING_WINDOW_START,
    )
    end = _entry_time(
        entry,
        CONF_WATERING_WINDOW_END,
        DEFAULT_WATERING_WINDOW_END,
    )
    if start == end:
        return False
    if start < end:
        return start <= current_time < end
    return current_time >= start or current_time < end


def _entry_time(
    entry: SolarIrrigationConfigEntry,
    key: str,
    default: str,
) -> time:
    """Read a time option from effective entry configuration."""
    raw = entry.options.get(key, entry.data.get(key, default))
    if isinstance(raw, time):
        return raw
    return time.fromisoformat(str(raw))


def _get_loaded_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> SolarIrrigationConfigEntry:
    """Resolve a loaded Solar Irrigation entry or raise a service error."""
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        raise HomeAssistantError(f"Solar Irrigation entry {entry_id} is not loaded")
    return entry  # type: ignore[return-value]
