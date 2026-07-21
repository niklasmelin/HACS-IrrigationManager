"""Tests for unit normalization and optional-rain calculations."""

from __future__ import annotations

from homeassistant.const import UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import CONF_RAIN_SENSOR
from custom_components.solar_irrigation.coordinator import SolarIrrigationCoordinator


async def test_calculation_without_rain(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that omitted rain uses a neutral factor and solar-only runtime."""
    mock_config_entry.add_to_hass(hass)
    hass.states.async_set(
        "sensor.solar_energy",
        "32500",
        {"unit_of_measurement": UnitOfEnergy.WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "0.01",
        {"unit_of_measurement": UnitOfEnergy.MEGA_WATT_HOUR},
    )
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    data = await coordinator._async_update_data()
    assert data.actual_solar_kwh == 32.5
    assert data.remaining_solar_kwh == 10
    assert data.rain_mm is None
    assert data.rain_factor == 1


async def test_rain_reduces_runtime(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that configured rain linearly reduces calculated runtime."""
    rain_entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_RAIN_SENSOR: "sensor.rain"},
        entry_id=mock_config_entry.entry_id,
    )
    rain_entry.add_to_hass(hass)
    hass.states.async_set(
        "sensor.solar_energy",
        "65",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "0",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.rain",
        "2.5",
        {"unit_of_measurement": UnitOfLength.MILLIMETERS},
    )
    coordinator = SolarIrrigationCoordinator(hass, rain_entry)
    data = await coordinator._async_update_data()
    assert data.rain_factor == 0.5
    assert data.runtime_minutes == 30


async def test_rain_threshold_skips_irrigation(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that rain at the threshold yields zero runtime and a skip reason."""
    rain_entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_RAIN_SENSOR: "sensor.rain"},
        entry_id=mock_config_entry.entry_id,
    )
    rain_entry.add_to_hass(hass)
    for entity_id in ("sensor.solar_energy", "sensor.remaining_solar_energy"):
        hass.states.async_set(
            entity_id,
            "65",
            {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
        )
    hass.states.async_set(
        "sensor.rain",
        "0.5",
        {"unit_of_measurement": UnitOfLength.CENTIMETERS},
    )
    data = await SolarIrrigationCoordinator(hass, rain_entry)._async_update_data()
    assert data.runtime_seconds == 0
    assert data.skip_reason == "rain_threshold_reached"
