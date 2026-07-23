"""Configuration and options flows for Solar Irrigation."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.valve import ValveEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_PULSE_DURATION,
    CONF_MAX_RUNTIME,
    CONF_MAX_SOLAR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SKIP_THRESHOLD,
    CONF_REMAINING_SENSOR,
    CONF_SOAK_DURATION,
    CONF_SOLAR_SENSOR,
    CONF_UPDATE_INTERVAL,
    CONF_WATERING_WINDOW_END,
    CONF_WATERING_WINDOW_START,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_MAX_SOLAR,
    DEFAULT_RAIN_SKIP_THRESHOLD,
    DEFAULT_SOAK_DURATION,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WATERING_WINDOW_END,
    DEFAULT_WATERING_WINDOW_START,
    DOMAIN,
    MAX_MAX_PULSE_DURATION,
    MAX_MAX_RUNTIME,
    MAX_MAX_SOLAR,
    MAX_RAIN_SKIP_THRESHOLD,
    MAX_SOAK_DURATION,
    MAX_UPDATE_INTERVAL,
    MIN_MAX_PULSE_DURATION,
    MIN_MAX_RUNTIME,
    MIN_MAX_SOLAR,
    MIN_RAIN_SKIP_THRESHOLD,
    MIN_SOAK_DURATION,
    MIN_UPDATE_INTERVAL,
    SUPPORTED_ENERGY_UNITS,
    SUPPORTED_RAIN_UNITS,
)
from .watering_window import entry_value


class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial configuration for Solar Irrigation."""

    VERSION = 3

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Validate user input and create a uniquely identified config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = _normalize_optional_values(user_input, preserve_clear=False)
            errors = _validate_input(self.hass, normalized)
            if not errors:
                irrigation_entity = str(normalized[CONF_IRRIGATION_ENTITY])
                await self.async_set_unique_id(irrigation_entity)
                self._abort_if_unique_id_configured()
                state = self.hass.states.get(irrigation_entity)
                display_name = state.name if state else irrigation_entity
                return self.async_create_entry(
                    title=f"Solar Irrigation - {display_name}",
                    data=normalized,
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
        """Validate and save changed options, including an explicitly cleared rain sensor."""
        current = {**self._entry.data, **self._entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            normalized = _normalize_optional_values(user_input, preserve_clear=True)
            # Peak daily water demand is edited through its writable number
            # entity, not duplicated in the options form. Preserve the effective
            # value when replacing the complete options dictionary.
            normalized[CONF_MAX_RUNTIME] = entry_value(
                self._entry,
                CONF_MAX_RUNTIME,
                DEFAULT_MAX_RUNTIME,
            )
            errors = _validate_input(self.hass, normalized)
            irrigation_entity = str(normalized.get(CONF_IRRIGATION_ENTITY, ""))
            if not errors and _irrigation_entity_is_used_by_other_entry(
                self.hass,
                irrigation_entity,
                exclude_entry_id=self._entry.entry_id,
            ):
                errors[CONF_IRRIGATION_ENTITY] = "already_configured"
            if not errors:
                if self._entry.unique_id != irrigation_entity:
                    runtime = getattr(self._entry, "runtime_data", None)
                    if runtime is not None:
                        runtime.suppress_next_reload = True
                    self.hass.config_entries.async_update_entry(
                        self._entry,
                        unique_id=irrigation_entity,
                    )
                return self.async_create_entry(title="", data=normalized)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(
                user_input or current,
                include_peak_daily_water_demand=False,
            ),
            errors=errors,
        )


def _schema(
    defaults: dict[str, Any] | None = None,
    *,
    include_peak_daily_water_demand: bool = True,
) -> vol.Schema:
    """Build the user-facing setup or options schema.

    Peak daily water demand is collected during initial setup, then maintained by
    its writable Home Assistant number entity. Hiding it from the options form
    prevents two competing user interfaces from changing the same seasonal value.
    """
    values = defaults or {}
    fields: dict[vol.Marker, Any] = {
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
                unit_of_measurement="kWh",
            )
        ),
    }
    if include_peak_daily_water_demand:
        fields[
            vol.Required(
                CONF_MAX_RUNTIME,
                default=values.get(CONF_MAX_RUNTIME, DEFAULT_MAX_RUNTIME),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_MAX_RUNTIME,
                max=MAX_MAX_RUNTIME,
                step=1,
                unit_of_measurement="min/day",
                mode=selector.NumberSelectorMode.BOX,
            )
        )

    fields.update(
        {
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
                CONF_MAX_PULSE_DURATION,
                default=values.get(
                    CONF_MAX_PULSE_DURATION,
                    DEFAULT_MAX_PULSE_DURATION,
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_MAX_PULSE_DURATION,
                    max=MAX_MAX_PULSE_DURATION,
                    step=1,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_SOAK_DURATION,
                default=values.get(CONF_SOAK_DURATION, DEFAULT_SOAK_DURATION),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SOAK_DURATION,
                    max=MAX_SOAK_DURATION,
                    step=1,
                    unit_of_measurement="min",
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
                CONF_WATERING_WINDOW_START,
                default=values.get(
                    CONF_WATERING_WINDOW_START,
                    DEFAULT_WATERING_WINDOW_START,
                ),
            ): selector.TimeSelector(),
            vol.Required(
                CONF_WATERING_WINDOW_END,
                default=values.get(
                    CONF_WATERING_WINDOW_END,
                    DEFAULT_WATERING_WINDOW_END,
                ),
            ): selector.TimeSelector(),
        }
    )
    return vol.Schema(fields)


def _normalize_optional_values(
    user_input: dict[str, Any],
    *,
    preserve_clear: bool,
) -> dict[str, Any]:
    """Normalize the optional rain sensor for setup or later removal.

    Initial setup omits an empty optional value. The options flow instead stores
    an explicit ``None`` so a rain sensor originally held in ``entry.data`` can
    be deliberately removed without falling back to the old value.
    """
    normalized = dict(user_input)
    rain_sensor = normalized.get(CONF_RAIN_SENSOR)
    if rain_sensor:
        normalized[CONF_RAIN_SENSOR] = rain_sensor
    elif preserve_clear:
        normalized[CONF_RAIN_SENSOR] = None
    else:
        normalized.pop(CONF_RAIN_SENSOR, None)
    return normalized


def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Return field-specific validation errors for entities and numeric limits."""
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

    _validate_irrigation_entity(
        hass,
        user_input.get(CONF_IRRIGATION_ENTITY),
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_MAX_SOLAR),
        CONF_MAX_SOLAR,
        MIN_MAX_SOLAR,
        MAX_MAX_SOLAR,
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_MAX_RUNTIME),
        CONF_MAX_RUNTIME,
        MIN_MAX_RUNTIME,
        MAX_MAX_RUNTIME,
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_RAIN_SKIP_THRESHOLD),
        CONF_RAIN_SKIP_THRESHOLD,
        MIN_RAIN_SKIP_THRESHOLD,
        MAX_RAIN_SKIP_THRESHOLD,
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_MAX_PULSE_DURATION),
        CONF_MAX_PULSE_DURATION,
        MIN_MAX_PULSE_DURATION,
        MAX_MAX_PULSE_DURATION,
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_SOAK_DURATION),
        CONF_SOAK_DURATION,
        MIN_SOAK_DURATION,
        MAX_SOAK_DURATION,
        errors,
    )
    _validate_number_range(
        user_input.get(CONF_UPDATE_INTERVAL),
        CONF_UPDATE_INTERVAL,
        MIN_UPDATE_INTERVAL,
        MAX_UPDATE_INTERVAL,
        errors,
    )
    _validate_watering_window(user_input, errors)
    return errors


def _validate_sensor(
    hass: HomeAssistant,
    entity_id: Any,
    supported_units: frozenset[str],
    field: str,
    errors: dict[str, str],
) -> None:
    """Validate that a sensor exists, is numeric, finite, and uses a known unit."""
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


def _validate_irrigation_entity(
    hass: HomeAssistant,
    entity_id: Any,
    errors: dict[str, str],
) -> None:
    """Validate actuator existence, availability, and supported domain."""
    if not entity_id or not isinstance(entity_id, str) or "." not in entity_id:
        errors[CONF_IRRIGATION_ENTITY] = "invalid_irrigation_entity"
        return
    domain = entity_id.split(".", 1)[0]
    state = hass.states.get(entity_id)
    if domain not in {"switch", "valve"} or state is None:
        errors[CONF_IRRIGATION_ENTITY] = "invalid_irrigation_entity"
        return
    if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE, ""}:
        errors[CONF_IRRIGATION_ENTITY] = "unavailable"
        return

    required_services = (
        ("open_valve", "close_valve")
        if domain == "valve"
        else ("turn_on", "turn_off")
    )
    if not all(
        hass.services.has_service(domain, service) for service in required_services
    ):
        errors[CONF_IRRIGATION_ENTITY] = "unsupported_irrigation_entity"
        return

    if domain == "valve":
        supported = ValveEntityFeature(
            int(state.attributes.get(ATTR_SUPPORTED_FEATURES, 0))
        )
        required = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        if supported & required != required:
            errors[CONF_IRRIGATION_ENTITY] = "unsupported_irrigation_entity"


def _validate_number_range(
    value: Any,
    field: str,
    minimum: float,
    maximum: float,
    errors: dict[str, str],
) -> None:
    """Validate a finite numeric value against the selector's exact range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[field] = "invalid_value"
        return
    if not math.isfinite(number) or not minimum <= number <= maximum:
        errors[field] = "invalid_value"


def _validate_watering_window(
    user_input: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Reject an empty or ambiguous watering window while allowing overnight use."""
    start = user_input.get(CONF_WATERING_WINDOW_START)
    end = user_input.get(CONF_WATERING_WINDOW_END)
    if start is not None and end is not None and str(start) == str(end):
        errors[CONF_WATERING_WINDOW_END] = "invalid_watering_window"


def _irrigation_entity_is_used_by_other_entry(
    hass: HomeAssistant,
    entity_id: str,
    *,
    exclude_entry_id: str,
) -> bool:
    """Return whether another entry already controls the selected actuator."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == exclude_entry_id:
            continue
        configured = str(entry_value(entry, CONF_IRRIGATION_ENTITY, ""))
        if configured == entity_id:
            return True
    return False
