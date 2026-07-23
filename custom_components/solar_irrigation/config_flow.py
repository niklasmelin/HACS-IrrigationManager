"""Configuration and options flows for Solar Irrigation."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_RUNTIME,
    CONF_MAX_SOLAR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SKIP_THRESHOLD,
    CONF_REMAINING_SENSOR,
    CONF_SCHEDULE_TIME,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    CONF_SOLAR_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_MAX_SOLAR,
    DEFAULT_RAIN_SKIP_THRESHOLD,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_MAX_RUNTIME,
    MAX_MAX_SOLAR,
    MAX_RAIN_SKIP_THRESHOLD,
    MAX_UPDATE_INTERVAL,
    MIN_MAX_RUNTIME,
    MIN_MAX_SOLAR,
    MIN_RAIN_SKIP_THRESHOLD,
    MIN_UPDATE_INTERVAL,
    SUPPORTED_ENERGY_UNITS,
    SUPPORTED_RAIN_UNITS,
)


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial configuration for Solar Irrigation."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Validate user input and create a uniquely identified config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                irrigation_entity = str(user_input[CONF_IRRIGATION_ENTITY])
                await self.async_set_unique_id(irrigation_entity)
                self._abort_if_unique_id_configured()
                title = self.hass.states.get(irrigation_entity)
                display_name = title.name if title else irrigation_entity
                return self.async_create_entry(
                    title=f"Solar Irrigation - {display_name}",
                    data=user_input,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SolarIrrigationOptionsFlow:
        """Return the options flow for an existing config entry."""
        return SolarIrrigationOptionsFlow(config_entry)


class SolarIrrigationOptionsFlow(config_entries.OptionsFlow):
    """Allow source entities and calculation settings to be updated."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow with current effective values."""
        self._entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Validate and save changed options."""
        current = {**self._entry.data, **self._entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_input(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current),
            errors=errors,
        )


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user-facing schema with an optional rain sensor."""
    values = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SOLAR_SENSOR,
                description={"suggested_value": values.get(CONF_SOLAR_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_REMAINING_SENSOR,
                description={"suggested_value": values.get(CONF_REMAINING_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_IRRIGATION_ENTITY,
                description={"suggested_value": values.get(CONF_IRRIGATION_ENTITY)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve"])
            ),
            vol.Optional(
                CONF_RAIN_SENSOR,
                description={"suggested_value": values.get(CONF_RAIN_SENSOR)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(
                CONF_MAX_SOLAR,
                default=values.get(CONF_MAX_SOLAR, DEFAULT_MAX_SOLAR),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_MAX_SOLAR,
                    max=MAX_MAX_SOLAR,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_MAX_RUNTIME,
                default=values.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_MAX_RUNTIME,
                    max=MAX_MAX_RUNTIME,
                    step=1,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_RAIN_SKIP_THRESHOLD,
                default=values.get(
                    CONF_RAIN_SKIP_THRESHOLD,
                    DEFAULT_RAIN_SKIP_THRESHOLD,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_RAIN_SKIP_THRESHOLD,
                    max=MAX_RAIN_SKIP_THRESHOLD,
                    step=0.1,
                    unit_of_measurement="mm",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=values.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=60,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SCHEDULE_TIME,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
                default=values.get(CONF_SCHEDULE_TIME, DEFAULT_SCHEDULE_TIME),
            ): selector.TimeSelector(),
        }
    )


def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return field-specific validation errors for configured entities and limits."""
    errors: dict[str, str] = {}
    _validate_sensor(
        hass,
        user_input.get(CONF_SOLAR_SENSOR),
        SUPPORTED_ENERGY_UNITS,
        CONF_SOLAR_SENSOR,
        errors,
    )
    _validate_sensor(
        hass,
        user_input.get(CONF_REMAINING_SENSOR),
        SUPPORTED_ENERGY_UNITS,
        CONF_REMAINING_SENSOR,
        errors,
    )
    rain_sensor = user_input.get(CONF_RAIN_SENSOR)
    if rain_sensor:
        _validate_sensor(
            hass,
            rain_sensor,
            SUPPORTED_RAIN_UNITS,
            CONF_RAIN_SENSOR,
            errors,
        )
    irrigation = user_input.get(CONF_IRRIGATION_ENTITY)
    if not irrigation or hass.states.get(irrigation) is None:
        errors[CONF_IRRIGATION_ENTITY] = "invalid_entity"
    for key in (CONF_MAX_SOLAR, CONF_RAIN_SKIP_THRESHOLD):
        _validate_positive(user_input.get(key), key, errors)
    _validate_non_negative(user_input.get(CONF_MAX_RUNTIME), CONF_MAX_RUNTIME, errors)
    _validate_positive(user_input.get(CONF_UPDATE_INTERVAL), CONF_UPDATE_INTERVAL, errors)
    _validate_watering_window(user_input, errors)
    return errors


def _validate_sensor(
    hass: HomeAssistant,
    entity_id: Any,
    supported_units: frozenset[str],
    field: str,
    errors: dict[str, str],
) -> None:
    """Validate that a sensor exists, is numeric, finite, and has a supported unit."""
    state = hass.states.get(str(entity_id)) if entity_id else None
    if state is None:
        errors[field] = "invalid_entity"
        return
    if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, ""}:
        errors[field] = "unavailable"
        return
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        errors[field] = "not_numeric"
        return
    if not math.isfinite(value) or value < 0:
        errors[field] = "invalid_value"
        return
    if state.attributes.get("unit_of_measurement") not in supported_units:
        errors[field] = "invalid_unit"


def _validate_positive(value: Any, field: str, errors: dict[str, str]) -> None:
    """Validate a finite numeric field that must be greater than zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[field] = "invalid_value"
        return
    if not math.isfinite(number) or number <= 0:
        errors[field] = "invalid_value"


def _validate_non_negative(value: Any, field: str, errors: dict[str, str]) -> None:
    """Validate a finite numeric field that may be zero but not negative."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[field] = "invalid_value"
        return
    if not math.isfinite(number) or number < 0:
        errors[field] = "invalid_value"


def _validate_watering_window(
    user_input: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Validate that automatic watering has a non-empty daily time window.

    Both daytime and overnight windows are valid. Equal values would represent
    either a zero-length or ambiguous 24-hour window, so they are rejected.
    """
    start = user_input.get(CONF_WATERING_WINDOW_START)
    end = user_input.get(CONF_WATERING_WINDOW_END)
    if start is None or end is None:
        return
    if str(start) == str(end):
        errors[CONF_WATERING_WINDOW_END] = "invalid_watering_window"
