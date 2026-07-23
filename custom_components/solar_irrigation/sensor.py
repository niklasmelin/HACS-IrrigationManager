"""Diagnostic sensor entities for Solar Irrigation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_RAIN_SENSOR, DOMAIN, ControllerStatus
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

SOLAR_HISTORY_DESCRIPTIONS: tuple[SolarIrrigationSensorDescription, ...] = (
    SolarIrrigationSensorDescription(
        key="solar_latest_delta",
        translation_key="solar_latest_delta",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_latest_delta_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="solar_energy_last_hour",
        translation_key="solar_energy_last_hour",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_energy_last_hour_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="solar_energy_last_2_hours",
        translation_key="solar_energy_last_2_hours",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_energy_last_2_hours_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="solar_rate_last_hour",
        translation_key="solar_rate_last_hour",
        native_unit_of_measurement="kWh/h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_rate_last_hour_kwh_per_hour,
    ),
    SolarIrrigationSensorDescription(
        key="solar_rate_last_2_hours",
        translation_key="solar_rate_last_2_hours",
        native_unit_of_measurement="kWh/h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_rate_last_2_hours_kwh_per_hour,
    ),
    SolarIrrigationSensorDescription(
        key="solar_rolling_rate",
        translation_key="solar_rolling_rate",
        native_unit_of_measurement="kWh/h",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda data: data.solar_rolling_rate_kwh_per_hour,
    ),
    SolarIrrigationSensorDescription(
        key="solar_sample_count",
        translation_key="solar_sample_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.solar_sample_count,
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
    descriptions = [*SENSOR_DESCRIPTIONS, *SOLAR_HISTORY_DESCRIPTIONS]
    if entry.options.get(CONF_RAIN_SENSOR, entry.data.get(CONF_RAIN_SENSOR)):
        descriptions.append(RAIN_DESCRIPTION)
    async_add_entities(
        SolarIrrigationSensor(entry, description) for description in descriptions
    )
    async_add_entities(
        (
            SolarIrrigationStatusSensor(entry),
            SolarHistorySensor(entry),
            DailyBudgetSensor(entry),
            DeliveredTodaySensor(entry),
            RemainingBudgetSensor(entry),
            PulseCountSensor(entry),
            DecisionReasonSensor(entry),
        )
    )


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
        """Return execution, water-budget, and solar-observation details."""
        data = self.entry.runtime_data.coordinator.data
        controller = self.entry.runtime_data.controller
        attributes = controller.state.as_dict()
        attributes.update(
            {
                "daily_budget_minutes": data.runtime_minutes,
                "delivered_today_minutes": round(
                    controller.delivered_today_seconds() / 60, 3
                ),
                "remaining_today_minutes": _remaining_budget(entry=self.entry),
                "pulse_count_today": controller.pulse_count_today(),
                "decision_reason": _decision_reason(self.entry),
                "solar_energy_last_hour_kwh": data.solar_energy_last_hour_kwh,
                "solar_energy_last_2_hours_kwh": data.solar_energy_last_2_hours_kwh,
                "solar_rolling_rate_kwh_per_hour": (
                    data.solar_rolling_rate_kwh_per_hour
                ),
                "solar_sample_count": data.solar_sample_count,
            }
        )
        return attributes


class SolarHistorySensor(CoordinatorEntity[SolarIrrigationCoordinator], SensorEntity):
    """Expose the full two-hour sample history as diagnostic attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "solar_history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the solar-history sensor."""
        super().__init__(entry.runtime_data.coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_solar_history"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the number of accepted samples in the history window."""
        return self.coordinator.data.solar_sample_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return baseline and timestamped sample details."""
        return self.coordinator.solar_history_as_dict()


class _ControllerMetricSensor(SensorEntity):
    """Base class for sensors combining coordinator and controller state."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: SolarIrrigationConfigEntry, key: str) -> None:
        """Initialize a stable controller metric entity."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)


class DailyBudgetSensor(_ControllerMetricSensor):
    """Expose today's calculated total irrigation budget."""

    _attr_translation_key = "daily_water_budget"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the daily-budget sensor."""
        super().__init__(entry, "daily_water_budget")

    @property
    def native_value(self) -> float:
        """Return the latest calculated daily runtime budget."""
        return self.entry.runtime_data.coordinator.data.runtime_minutes


class DeliveredTodaySensor(_ControllerMetricSensor):
    """Expose measured irrigation runtime delivered today."""

    _attr_translation_key = "delivered_today"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the delivered-today sensor."""
        super().__init__(entry, "delivered_today")

    @property
    def native_value(self) -> float:
        """Return today's measured delivered runtime."""
        return round(self.entry.runtime_data.controller.delivered_today_seconds() / 60, 3)


class RemainingBudgetSensor(_ControllerMetricSensor):
    """Expose today's remaining irrigation runtime budget."""

    _attr_translation_key = "remaining_water_budget"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the remaining-budget sensor."""
        super().__init__(entry, "remaining_water_budget")

    @property
    def native_value(self) -> float:
        """Return calculated budget minus measured delivery."""
        return _remaining_budget(self.entry)


class PulseCountSensor(_ControllerMetricSensor):
    """Expose the number of irrigation starts today."""

    _attr_translation_key = "pulse_count_today"

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the pulse-count sensor."""
        super().__init__(entry, "pulse_count_today")

    @property
    def native_value(self) -> int:
        """Return today's pulse count."""
        return self.entry.runtime_data.controller.pulse_count_today()


class DecisionReasonSensor(_ControllerMetricSensor):
    """Explain why the controller is running, ready, waiting, or blocked."""

    _attr_translation_key = "decision_reason"

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the decision-reason sensor."""
        super().__init__(entry, "decision_reason")

    @property
    def native_value(self) -> str:
        """Return the current explainable controller decision."""
        return _decision_reason(self.entry)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the values used to derive the decision."""
        data = self.entry.runtime_data.coordinator.data
        return {
            "daily_budget_minutes": data.runtime_minutes,
            "delivered_today_minutes": round(
                self.entry.runtime_data.controller.delivered_today_seconds() / 60, 3
            ),
            "remaining_today_minutes": _remaining_budget(self.entry),
            "skip_reason": data.skip_reason,
            "last_skip_reason": (
                self.entry.runtime_data.controller.state.last_skip_reason
            ),
            "solar_sample_count": data.solar_sample_count,
            "solar_energy_last_hour_kwh": data.solar_energy_last_hour_kwh,
            "solar_energy_last_2_hours_kwh": data.solar_energy_last_2_hours_kwh,
        }


def _remaining_budget(entry: SolarIrrigationConfigEntry) -> float:
    """Return the non-negative calculated runtime still available today."""
    budget = entry.runtime_data.coordinator.data.runtime_minutes
    delivered = entry.runtime_data.controller.delivered_today_seconds() / 60
    return round(max(0.0, budget - delivered), 3)


def _decision_reason(entry: SolarIrrigationConfigEntry) -> str:
    """Return a concise explanation of the current controller decision."""
    controller = entry.runtime_data.controller
    data = entry.runtime_data.coordinator.data
    if controller.state.status is ControllerStatus.IRRIGATING:
        return "irrigation_running"
    if controller.state.status is ControllerStatus.ERROR:
        return "controller_error"
    if data.solar_sample_count == 0:
        return "collecting_solar_history"
    if data.skip_reason is not None:
        return data.skip_reason
    if _remaining_budget(entry) <= 0:
        return "daily_budget_exhausted"
    if controller.automatic_decision_made_today():
        return "automatic_decision_completed"
    return "ready_for_schedule"


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared device information for all entities in one entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Solar Irrigation",
        model="Irrigation Manager",
    )
