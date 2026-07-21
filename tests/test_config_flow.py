"""Tests for Solar Irrigation configuration and optional rain input."""

from __future__ import annotations

from homeassistant.const import UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.solar_irrigation.const import (
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_RUNTIME,
    CONF_MAX_SOLAR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SKIP_THRESHOLD,
    CONF_REMAINING_SENSOR,
    CONF_SCHEDULE_TIME,
    CONF_SOLAR_SENSOR,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)


def _valid_input(*, include_rain: bool) -> dict[str, object]:
    """Return valid flow input with optional rain configuration."""
    data: dict[str, object] = {
        CONF_SOLAR_SENSOR: "sensor.solar_energy",
        CONF_REMAINING_SENSOR: "sensor.remaining_solar_energy",
        CONF_IRRIGATION_ENTITY: "switch.irrigation_valve",
        CONF_MAX_SOLAR: 65.0,
        CONF_MAX_RUNTIME: 60.0,
        CONF_RAIN_SKIP_THRESHOLD: 5.0,
        CONF_UPDATE_INTERVAL: 3600,
        CONF_SCHEDULE_TIME: "06:00:00",
    }
    if include_rain:
        data[CONF_RAIN_SENSOR] = "sensor.rain"
    return data


def _set_valid_states(hass: HomeAssistant, *, include_rain: bool) -> None:
    """Create valid source and actuator states for config-flow validation."""
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
