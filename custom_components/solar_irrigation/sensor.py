"""Diagnostic sensor entities for Solar Irrigation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_RAIN_SENSOR, DOMAIN
from .coordinator import SolarIrrigationCoordinator
from .models import SolarIrrigationConfigEntry, SolarIrrigationData


@dataclass(frozen=True, kw_only=True)
class SolarIrrigationSensorDescription(SensorEntityDescription):
    """Describe how a coordinator field is exposed as a sensor."""

    value_fn: Callable[[SolarIrrigationData], Any]


SENSOR_DESCRIPTIONS: tuple[SolarIrrigationSensorDescription, ...] = (
    SolarIrrigationSensorDescription(
        key="actual_solar",
        translation_key="actual_solar",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.actual_solar_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="remaining_solar",
        translation_key="remaining_solar",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.remaining_solar_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="expected_solar_today",
        translation_key="expected_solar_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.expected_solar_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="solar_scale_factor",
        translation_key="solar_scale_factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: round(data.solar_factor * 100, 1),
    ),
    SolarIrrigationSensorDescription(
        key="rain_factor",
        translation_key="rain_factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: round(data.rain_factor * 100, 1),
    ),
    SolarIrrigationSensorDescription(
        key="irrigation_runtime",
        translation_key="irrigation_runtime",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.runtime_minutes,
    ),
)

RAIN_DESCRIPTION = SolarIrrigationSensorDescription(
    key="rain_amount",
    translation_key="rain_amount",
    native_unit_of_measurement=UnitOfLength.MILLIMETERS,
    device_class=SensorDeviceClass.PRECIPITATION,
    state_class=SensorStateClass.TOTAL,
    value_fn=lambda data: data.rain_mm,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create coordinator-backed sensors for one config entry."""
    del hass
    descriptions = list(SENSOR_DESCRIPTIONS)
    if entry.options.get(CONF_RAIN_SENSOR, entry.data.get(CONF_RAIN_SENSOR)):
        descriptions.append(RAIN_DESCRIPTION)
    async_add_entities(
        SolarIrrigationSensor(entry, description) for description in descriptions
    )
    async_add_entities((SolarIrrigationStatusSensor(entry),))


class SolarIrrigationSensor(
    CoordinatorEntity[SolarIrrigationCoordinator],
    SensorEntity,
):
    """Expose one typed coordinator calculation value."""

    entity_description: SolarIrrigationSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: SolarIrrigationConfigEntry,
        description: SolarIrrigationSensorDescription,
    ) -> None:
        """Initialize a sensor with stable identity and shared device metadata."""
        super().__init__(entry.runtime_data.coordinator)
        self.entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        """Return the current native sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class SolarIrrigationStatusSensor(SensorEntity):
    """Expose controller status and recent execution details."""

    _attr_has_entity_name = True
    _attr_translation_key = "irrigation_status"

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the controller-status sensor."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_irrigation_status"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        """Return the current controller status value."""
        return self.entry.runtime_data.controller.state.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return execution timestamps, skip reason, and last error."""
        return self.entry.runtime_data.controller.state.as_dict()


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared device information for all entities in one entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Solar Irrigation",
        model="Irrigation Manager",
    )
