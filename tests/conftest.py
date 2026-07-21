"""Shared pytest fixtures for Solar Irrigation tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request: pytest.FixtureRequest) -> None:
    """Enable custom integrations only for Home Assistant behavior tests.

    Repository validation tests intentionally remain runnable with plain
    pytest and do not require the Home Assistant test package to be imported.
    """
    if request.node.get_closest_marker("repository_validation") is not None:
        return

    request.getfixturevalue("enable_custom_integrations")


@pytest.fixture
def config_entry_data() -> dict[str, Any]:
    """Return representative config-entry data using production constants."""
    from custom_components.solar_irrigation.const import (
        CONF_IRRIGATION_ENTITY,
        CONF_MAX_RUNTIME,
        CONF_MAX_SOLAR,
        CONF_REMAINING_SENSOR,
        CONF_SOLAR_SENSOR,
        CONF_UPDATE_INTERVAL,
        DEFAULT_MAX_RUNTIME,
        DEFAULT_MAX_SOLAR,
        DEFAULT_UPDATE_INTERVAL,
    )

    return {
        CONF_SOLAR_SENSOR: "sensor.solar_energy",
        CONF_REMAINING_SENSOR: "sensor.remaining_solar_energy",
        CONF_IRRIGATION_ENTITY: "switch.irrigation_valve",
        CONF_MAX_SOLAR: DEFAULT_MAX_SOLAR,
        CONF_MAX_RUNTIME: DEFAULT_MAX_RUNTIME,
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
    }


@pytest.fixture
def mock_config_entry(config_entry_data: dict[str, Any]):
    """Create a representative Solar Irrigation config entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solar_irrigation.const import DOMAIN

    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Irrigation Manager",
        unique_id="test-irrigation-manager",
        data=config_entry_data,
        options={},
        entry_id="test-entry-id",
    )


@pytest.fixture
def mock_coordinator_refresh() -> Generator[None, None, None]:
    """Prevent setup tests from accessing real sensors or devices."""
    with patch(
        "custom_components.solar_irrigation.coordinator."
        "SolarIrrigationCoordinator.async_config_entry_first_refresh",
        return_value=None,
    ):
        yield
