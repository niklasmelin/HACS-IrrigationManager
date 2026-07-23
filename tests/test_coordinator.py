"""Tests for calculation, history sampling, units, and optional rain."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import UnitOfEnergy, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import (
    CONF_MAX_RUNTIME,
    CONF_RAIN_SENSOR,
)
from custom_components.solar_irrigation.coordinator import SolarIrrigationCoordinator
from custom_components.solar_irrigation.models import SolarHistoryState


async def test_calculation_without_rain(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test actual plus remaining forecast and neutral optional-rain behavior."""
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
    assert data.expected_solar_kwh == 42.5
    assert data.rain_mm is None
    assert data.rain_factor == 1
    assert data.runtime_minutes == round(42.5 / 65 * 60, 3)


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


async def test_explicit_none_option_removes_data_rain_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that an options None prevents fallback to an initial rain sensor."""
    entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_RAIN_SENSOR: "sensor.rain"},
        options={CONF_RAIN_SENSOR: None},
    )
    entry.add_to_hass(hass)
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

    data = await SolarIrrigationCoordinator(hass, entry)._async_update_data()

    assert data.rain_mm is None
    assert data.rain_factor == 1


async def test_dry_budget_ignores_an_unavailable_configured_rain_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test Ignore rain can calculate from solar inputs without reading rain."""
    entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_RAIN_SENSOR: "sensor.rain"},
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "sensor.solar_energy",
        "20",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "12.5",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.rain",
        "unavailable",
        {"unit_of_measurement": UnitOfLength.MILLIMETERS},
    )
    coordinator = SolarIrrigationCoordinator(hass, entry)
    coordinator._history_store.async_save = AsyncMock()

    assert await coordinator.async_calculate_dry_budget_seconds() == 1800


async def test_delayed_sample_is_proportioned_into_rolling_windows(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test balanced use of a valid accumulated delta after missed samples."""
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    coordinator._history_loaded = True
    coordinator._history_store.async_save = AsyncMock()
    start = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    end = start + timedelta(hours=3)
    coordinator.solar_history = SolarHistoryState(
        baseline_energy_kwh=10,
        baseline_at=start,
    )

    await coordinator._async_sample_solar(16, end)
    metrics = coordinator._history_metrics(end)

    assert metrics["latest_delta"] == 6
    assert metrics["energy_last_hour"] == 2
    assert metrics["energy_last_2_hours"] == 4
    assert metrics["rate_last_hour"] == 2
    assert metrics["rate_last_2_hours"] == 2


async def test_cumulative_reset_rebuilds_history_from_midnight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a reset uses today's exact cumulative total without a negative delta."""
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    coordinator._history_loaded = True
    coordinator._history_store.async_save = AsyncMock()
    start = datetime(2026, 7, 23, 23, 45, tzinfo=UTC)
    coordinator.solar_history = SolarHistoryState(
        baseline_energy_kwh=50,
        baseline_at=start,
    )

    await coordinator._async_sample_solar(0.1, start + timedelta(minutes=15))

    assert coordinator.solar_history.baseline_energy_kwh == 0.1
    assert len(coordinator.solar_history.samples) == 1
    assert coordinator.solar_history.samples[0].delta_energy_kwh == 0.1


async def test_first_measurement_preserves_accumulated_energy_since_midnight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test history can use the valid cumulative total after restart or setup."""
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    coordinator._history_loaded = True
    coordinator._history_store.async_save = AsyncMock()
    timestamp = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

    await coordinator._async_sample_solar(12, timestamp)
    metrics = coordinator._history_metrics(timestamp)

    assert coordinator.solar_history.baseline_energy_kwh == 12
    assert len(coordinator.solar_history.samples) == 1
    assert coordinator.solar_history.samples[0].delta_energy_kwh == 12
    assert metrics["energy_last_2_hours"] > 0


async def test_new_local_day_rebaselines_even_when_value_is_higher(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a hidden overnight reset cannot become a cross-day positive delta."""
    coordinator = SolarIrrigationCoordinator(hass, mock_config_entry)
    coordinator._history_loaded = True
    coordinator._history_store.async_save = AsyncMock()
    baseline = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
    coordinator.solar_history = SolarHistoryState(
        baseline_energy_kwh=10,
        baseline_at=baseline,
    )

    await coordinator._async_sample_solar(20, baseline + timedelta(days=1))

    assert coordinator.solar_history.baseline_energy_kwh == 20
    assert len(coordinator.solar_history.samples) == 1
    assert coordinator.solar_history.samples[0].delta_energy_kwh == 20


async def test_invalid_peak_daily_demand_is_rejected_at_runtime(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test runtime validation protects entries that bypass the UI selector."""
    entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        unique_id=mock_config_entry.unique_id,
        data={**mock_config_entry.data, CONF_MAX_RUNTIME: 500},
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "sensor.solar_energy",
        "10",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )
    hass.states.async_set(
        "sensor.remaining_solar_energy",
        "10",
        {"unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    )

    with pytest.raises(UpdateFailed, match="Peak daily water demand"):
        await SolarIrrigationCoordinator(hass, entry)._async_update_data()
