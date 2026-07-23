"""Tests for Solar Irrigation configuration and options validation."""

from __future__ import annotations

from homeassistant.components.valve import ValveEntityFeature
from homeassistant.const import ATTR_SUPPORTED_FEATURES, UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import (
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
    DOMAIN,
)


def _noop_service(call: ServiceCall) -> None:
    """Provide a registered actuator service for config-flow validation."""
    del call


def _register_switch_services(hass: HomeAssistant) -> None:
    """Register the standard switch services required by the validator."""
    hass.services.async_register("switch", "turn_on", _noop_service)
    hass.services.async_register("switch", "turn_off", _noop_service)


def _valid_input(*, include_rain: bool) -> dict[str, object]:
    """Return valid flow input with optional rain configuration."""
    data: dict[str, object] = {
        CONF_SOLAR_SENSOR: "sensor.solar_energy",
        CONF_REMAINING_SENSOR: "sensor.remaining_solar_energy",
        CONF_IRRIGATION_ENTITY: "switch.irrigation_valve",
        CONF_MAX_SOLAR: 65.0,
        CONF_MAX_RUNTIME: 60.0,
        CONF_RAIN_SKIP_THRESHOLD: 5.0,
        CONF_MAX_PULSE_DURATION: 3.0,
        CONF_SOAK_DURATION: 15.0,
        CONF_UPDATE_INTERVAL: 3600,
        CONF_WATERING_WINDOW_START: "05:00:00",
        CONF_WATERING_WINDOW_END: "22:00:00",
    }
    if include_rain:
        data[CONF_RAIN_SENSOR] = "sensor.rain"
    return data


def _valid_options_input(*, include_rain: bool) -> dict[str, object]:
    """Return options input without the number-entity-owned peak demand."""
    data = _valid_input(include_rain=include_rain)
    data.pop(CONF_MAX_RUNTIME)
    return data


def _set_valid_states(hass: HomeAssistant, *, include_rain: bool) -> None:
    """Create valid source, actuator, and service states for validation."""
    _register_switch_services(hass)
    hass.states.async_set(
        "sensor.solar_energy",
        "10",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "20",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set("switch.irrigation_valve", "off")
    if include_rain:
        hass.states.async_set(
            "sensor.rain",
            "1",
            {"unit_of_measurement": UnitOfLength.MILLIMETERS},
        )


async def test_create_entry_without_rain(hass: HomeAssistant) -> None:
    """Test that the optional rain sensor may be omitted completely."""
    _set_valid_states(hass, include_rain=False)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=_valid_input(include_rain=False),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_RAIN_SENSOR not in result["data"]


async def test_create_entry_with_rain(hass: HomeAssistant) -> None:
    """Test successful configuration with a valid rain sensor."""
    _set_valid_states(hass, include_rain=True)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=_valid_input(include_rain=True),
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RAIN_SENSOR] == "sensor.rain"


async def test_options_can_remove_initial_rain_sensor(hass: HomeAssistant) -> None:
    """Test that an options value of None overrides rain stored in entry data."""
    _set_valid_states(hass, include_rain=True)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Rain entry",
        unique_id="switch.irrigation_valve",
        data=_valid_input(include_rain=True),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_valid_options_input(include_rain=False),
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RAIN_SENSOR] is None
    assert result["data"][CONF_MAX_RUNTIME] == 60.0


async def test_options_reject_actuator_used_by_other_entry(
    hass: HomeAssistant,
) -> None:
    """Test that two config entries cannot be changed to the same actuator."""
    _set_valid_states(hass, include_rain=False)
    hass.states.async_set("switch.other_irrigation", "off")
    first = MockConfigEntry(
        domain=DOMAIN,
        title="First",
        unique_id="switch.irrigation_valve",
        data=_valid_input(include_rain=False),
    )
    second_data = _valid_input(include_rain=False)
    second_data[CONF_IRRIGATION_ENTITY] = "switch.other_irrigation"
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Second",
        unique_id="switch.other_irrigation",
        data=second_data,
    )
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    changed = _valid_options_input(include_rain=False)
    changed[CONF_IRRIGATION_ENTITY] = "switch.other_irrigation"
    result = await hass.config_entries.options.async_init(first.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=changed,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_IRRIGATION_ENTITY] == "already_configured"


async def test_reject_invalid_rain_unit(hass: HomeAssistant) -> None:
    """Test that configured rain must use a supported precipitation unit."""
    _set_valid_states(hass, include_rain=True)
    hass.states.async_set(
        "sensor.rain",
        "1",
        {"unit_of_measurement": "kWh"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=_valid_input(include_rain=True),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_RAIN_SENSOR] == "invalid_unit"


async def test_reject_equal_watering_window_times(hass: HomeAssistant) -> None:
    """Test that a zero-length automatic watering window is rejected."""
    _set_valid_states(hass, include_rain=False)
    user_input = _valid_input(include_rain=False)
    user_input[CONF_WATERING_WINDOW_END] = user_input[CONF_WATERING_WINDOW_START]

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=user_input,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_WATERING_WINDOW_END] == "invalid_watering_window"


async def test_reject_out_of_range_values(hass: HomeAssistant) -> None:
    """Test exact backend enforcement of selector numeric limits."""
    _set_valid_states(hass, include_rain=False)
    user_input = _valid_input(include_rain=False)
    user_input[CONF_MAX_RUNTIME] = 9
    user_input[CONF_MAX_PULSE_DURATION] = 31
    user_input[CONF_SOAK_DURATION] = 0

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=user_input,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_MAX_RUNTIME] == "invalid_value"
    assert result["errors"][CONF_MAX_PULSE_DURATION] == "invalid_value"
    assert result["errors"][CONF_SOAK_DURATION] == "invalid_value"


async def test_reject_wrong_or_unavailable_actuator(hass: HomeAssistant) -> None:
    """Test backend actuator-domain and availability checks."""
    _set_valid_states(hass, include_rain=False)
    user_input = _valid_input(include_rain=False)
    hass.states.async_set("sensor.not_a_switch", "off")
    user_input[CONF_IRRIGATION_ENTITY] = "sensor.not_a_switch"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=user_input,
    )
    assert result["errors"][CONF_IRRIGATION_ENTITY] == "invalid_irrigation_entity"

    user_input[CONF_IRRIGATION_ENTITY] = "switch.irrigation_valve"
    hass.states.async_set("switch.irrigation_valve", "unavailable")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=user_input,
    )
    assert result["errors"][CONF_IRRIGATION_ENTITY] == "unavailable"


async def test_reject_actuator_without_control_services(hass: HomeAssistant) -> None:
    """Test that an entity without both control services is rejected."""
    hass.states.async_set(
        "sensor.solar_energy",
        "10",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "20",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set("switch.irrigation_valve", "off")
    hass.services.async_register("switch", "turn_on", _noop_service)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=_valid_input(include_rain=False),
    )

    assert result["type"] is FlowResultType.FORM
    assert (
        result["errors"][CONF_IRRIGATION_ENTITY]
        == "unsupported_irrigation_entity"
    )


async def test_reject_valve_without_open_and_close_features(
    hass: HomeAssistant,
) -> None:
    """Test valve selection requires entity-level open and close support."""
    _set_valid_states(hass, include_rain=False)
    hass.services.async_register("valve", "open_valve", _noop_service)
    hass.services.async_register("valve", "close_valve", _noop_service)
    hass.states.async_set(
        "valve.irrigation",
        "closed",
        {
            ATTR_SUPPORTED_FEATURES: int(ValveEntityFeature.OPEN),
        },
    )
    user_input = _valid_input(include_rain=False)
    user_input[CONF_IRRIGATION_ENTITY] = "valve.irrigation"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data=user_input,
    )

    assert result["type"] is FlowResultType.FORM
    assert (
        result["errors"][CONF_IRRIGATION_ENTITY]
        == "unsupported_irrigation_entity"
    )
