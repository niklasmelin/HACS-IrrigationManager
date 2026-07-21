"""Shared pytest fixtures for Solar Irrigation tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation.const import DOMAIN


pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading integrations from custom_components."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a representative Solar Irrigation config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Irrigation Manager",
        unique_id="test-irrigation-manager",
        data={
            # Replace these with the actual required config-flow fields.
            "temperature_sensor": "sensor.outdoor_temperature",
            "rain_sensor": "sensor.rain_today",
            "solar_sensor": "sensor.solar_energy",
            "irrigation_switch": "switch.irrigation_valve",
        },
        options={},
        entry_id="test-entry-id",
    )


@pytest.fixture
def mock_coordinator_refresh() -> Generator[None]:
    """Prevent setup tests from accessing real sensors or devices.

    Update the patch target when the coordinator implementation is finalized.
    """
    with patch(
        "custom_components.solar_irrigation.coordinator."
        "SolarIrrigationCoordinator.async_config_entry_first_refresh",
        return_value=None,
    ):
        yield