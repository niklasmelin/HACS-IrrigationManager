"""Solar Irrigation integration setup, services, and scheduling."""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .const import (
    CONF_DURATION,
    CONF_ENTRY_ID,
    CONF_IGNORE_RAIN,
    CONF_SCHEDULE_TIME,
    DEFAULT_SCHEDULE_TIME,
    DOMAIN,
    PLATFORMS,
    SVC_RUN_NOW,
    SVC_STOP,
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
    """Set up domain services exactly once for all config entries."""
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Create entry-owned runtime objects and forward entity platforms."""
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
    runtime.cancel_schedule = _schedule_daily_run(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
) -> bool:
    """Unload platforms and safely release only this entry's resources."""
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
    """Reload a config entry after its options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


def _schedule_daily_run(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
):
    """Schedule one automatic irrigation decision at the configured local time."""
    configured = str(
        entry.options.get(
            CONF_SCHEDULE_TIME,
            entry.data.get(CONF_SCHEDULE_TIME, DEFAULT_SCHEDULE_TIME),
        )
    )
    scheduled_time = time.fromisoformat(configured)

    async def async_daily_run(_now) -> None:
        """Refresh inputs and perform today's automatic irrigation decision."""
        controller = entry.runtime_data.controller
        if controller.automatic_decision_made_today():
            return
        await entry.runtime_data.coordinator.async_request_refresh()
        if not entry.runtime_data.coordinator.last_update_success:
            _LOGGER.warning(
                "Automatic irrigation skipped because source data is unavailable"
            )
            return
        await controller.async_run(automatic=True)

    return async_track_time_change(
        hass,
        async_daily_run,
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=scheduled_time.second,
    )


def _get_loaded_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> SolarIrrigationConfigEntry:
    """Resolve a loaded Solar Irrigation entry or raise a service error."""
    entry: ConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        raise HomeAssistantError(f"Solar Irrigation entry {entry_id} is not loaded")
    return entry  # type: ignore[return-value]
