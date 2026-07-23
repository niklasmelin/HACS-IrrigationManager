"""Shared pytest fixtures for Solar Irrigation tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    """Enable custom integrations only for Home Assistant behavior tests."""
    if request.node.get_closest_marker("repository_validation") is None:
        request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def config_entry_data() -> dict[str, Any]:
    """Return valid configuration without the optional rain sensor."""
    from custom_components.solar_irrigation.const import (
        CONF_IRRIGATION_ENTITY,
        CONF_MAX_PULSE_DURATION,
        CONF_MAX_RUNTIME,
        CONF_MAX_SOLAR,
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
    )

    return {
        CONF_SOLAR_SENSOR: "sensor.solar_energy",
        CONF_REMAINING_SENSOR: "sensor.remaining_solar_energy",
        CONF_IRRIGATION_ENTITY: "switch.irrigation_valve",
        CONF_MAX_SOLAR: DEFAULT_MAX_SOLAR,
        CONF_MAX_RUNTIME: DEFAULT_MAX_RUNTIME,
        CONF_RAIN_SKIP_THRESHOLD: DEFAULT_RAIN_SKIP_THRESHOLD,
        CONF_MAX_PULSE_DURATION: DEFAULT_MAX_PULSE_DURATION,
        CONF_SOAK_DURATION: DEFAULT_SOAK_DURATION,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_WATERING_WINDOW_START: DEFAULT_WATERING_WINDOW_START,
        CONF_WATERING_WINDOW_END: DEFAULT_WATERING_WINDOW_END,
    }


@pytest.fixture
def mock_config_entry(config_entry_data: dict[str, Any]):
    """Create a representative config entry using production keys."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solar_irrigation.const import DOMAIN

    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Irrigation Manager",
        unique_id="switch.irrigation_valve",
        data=config_entry_data,
        options={},
        entry_id="test-entry-id",
    )
