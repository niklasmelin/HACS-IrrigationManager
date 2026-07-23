"""Calculation, history, controller, and observability sensors."""

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
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAX_PULSE_DURATION,
    CONF_RAIN_SENSOR,
    CONF_SOAK_DURATION,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_SOAK_DURATION,
    DOMAIN,
    ControllerStatus,
)
from .coordinator import SolarIrrigationCoordinator
from .models import SolarIrrigationConfigEntry, SolarIrrigationData
from .watering_window import entry_value


@dataclass(frozen=True, kw_only=True)
class SolarIrrigationSensorDescription(SensorEntityDescription):
    """Describe how one coordinator field is exposed as a sensor."""

    value_fn: Callable[[SolarIrrigationData], Any]


SENSOR_DESCRIPTIONS: tuple[SolarIrrigationSensorDescription, ...] = (
    SolarIrrigationSensorDescription(
        key="actual_solar",
        translation_key="actual_solar",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.actual_solar_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="remaining_solar",
        translation_key="remaining_solar",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.remaining_solar_kwh,
    ),
    SolarIrrigationSensorDescription(
        key="expected_solar_today",
        translation_key="expected_solar_today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
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
    """Create coordinator and controller-backed sensors for one entry."""
    del hass
    descriptions = [*SENSOR_DESCRIPTIONS, *SOLAR_HISTORY_DESCRIPTIONS]
    if entry_value(entry, CONF_RAIN_SENSOR, None):
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
        """Initialize a sensor with stable identity and device metadata."""
        super().__init__(entry.runtime_data.coordinator)
        self.entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> Any:
        """Return the current native coordinator value."""
        return self.entity_description.value_fn(self.coordinator.data)


class _ControllerCoordinatorSensor(
    CoordinatorEntity[SolarIrrigationCoordinator],
    SensorEntity,
):
    """Base entity updated by both coordinator refreshes and controller pushes."""

    _attr_has_entity_name = True

    def __init__(self, entry: SolarIrrigationConfigEntry, key: str) -> None:
        """Initialize shared coordinator, controller, identity, and device data."""
        super().__init__(entry.runtime_data.coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = _device_info(entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller transitions after the entity is registered."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.entry.runtime_data.controller.async_add_listener(
                self._handle_controller_update
            )
        )

    @callback
    def _handle_controller_update(self) -> None:
        """Write state immediately after a controller transition."""
        self.async_write_ha_state()


class SolarIrrigationStatusSensor(_ControllerCoordinatorSensor):
    """Expose the current controller mode and detailed event state."""

    _attr_translation_key = "irrigation_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [status.value for status in ControllerStatus]

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the controller-status sensor."""
        super().__init__(entry, "irrigation_status")

    @property
    def native_value(self) -> str:
        """Return the current controller status value."""
        return self.entry.runtime_data.controller.state.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return event, water-budget, error, and solar-observation details."""
        data = self.coordinator.data
        controller = self.entry.runtime_data.controller
        attributes = controller.state.as_dict()
        attributes.update(
            {
                "daily_budget_minutes": data.runtime_minutes,
                "delivered_today_minutes": round(
                    controller.delivered_today_seconds() / 60, 3
                ),
                "remaining_today_minutes": _remaining_budget(self.entry),
                "pulse_count_today": controller.pulse_count_today(),
                "decision_reason": _decision_reason(self.entry),
                "decision_code": controller.state.decision_reason,
                "error_message": controller.state.last_error,
                "actuator_state": controller.actuator_state,
                "actuator_is_active": controller.actuator_is_active,
                "maximum_pulse_minutes": float(
                    entry_value(
                        self.entry,
                        CONF_MAX_PULSE_DURATION,
                        DEFAULT_MAX_PULSE_DURATION,
                    )
                ),
                "soak_minutes": float(
                    entry_value(
                        self.entry,
                        CONF_SOAK_DURATION,
                        DEFAULT_SOAK_DURATION,
                    )
                ),
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


class _ControllerMetricSensor(_ControllerCoordinatorSensor):
    """Base class for diagnostic sensors combining calculation and execution."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC


class DailyBudgetSensor(_ControllerMetricSensor):
    """Expose the current calculated total irrigation budget for today."""

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
        return self.coordinator.data.runtime_minutes


class DeliveredTodaySensor(_ControllerMetricSensor):
    """Expose measured pump-on runtime accumulated today."""

    _attr_translation_key = "delivered_today"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the delivered-today sensor."""
        super().__init__(entry, "delivered_today")

    @property
    def native_value(self) -> float:
        """Return today's accumulated measured delivery."""
        return round(self.entry.runtime_data.controller.delivered_today_seconds() / 60, 3)


class RemainingBudgetSensor(_ControllerMetricSensor):
    """Expose calculated budget not yet delivered during the local day."""

    _attr_translation_key = "remaining_water_budget"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the remaining-budget sensor."""
        super().__init__(entry, "remaining_water_budget")

    @property
    def native_value(self) -> float:
        """Return current budget minus all manual and automatic delivery."""
        return _remaining_budget(self.entry)


class PulseCountSensor(_ControllerMetricSensor):
    """Expose the number of confirmed pump-on pulses today."""

    _attr_translation_key = "pulse_count_today"

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize the pulse-count sensor."""
        super().__init__(entry, "pulse_count_today")

    @property
    def native_value(self) -> int:
        """Return today's confirmed pulse count."""
        return self.entry.runtime_data.controller.pulse_count_today()


class DecisionReasonSensor(_ControllerMetricSensor):
    """Explain why the controller is watering, soaking, waiting, or blocked."""

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
        """Return values used to derive the current controller decision."""
        data = self.coordinator.data
        controller = self.entry.runtime_data.controller
        return {
            "daily_budget_minutes": data.runtime_minutes,
            "delivered_today_minutes": round(
                controller.delivered_today_seconds() / 60, 3
            ),
            "remaining_today_minutes": _remaining_budget(self.entry),
            "skip_reason": data.skip_reason,
            "last_skip_reason": controller.state.last_skip_reason,
            "last_result": controller.state.last_result,
            "decision_code": controller.state.decision_reason,
            "error_message": controller.state.last_error,
            "actuator_state": controller.actuator_state,
            "actuator_is_active": controller.actuator_is_active,
            "cycle_remaining_minutes": round(
                controller.state.cycle_remaining_seconds / 60, 3
            ),
            "next_pulse_at": (
                controller.state.next_pulse_at.isoformat()
                if controller.state.next_pulse_at
                else None
            ),
            "solar_sample_count": data.solar_sample_count,
            "solar_energy_last_hour_kwh": data.solar_energy_last_hour_kwh,
            "solar_energy_last_2_hours_kwh": data.solar_energy_last_2_hours_kwh,
        }


def _remaining_budget(entry: SolarIrrigationConfigEntry) -> float:
    """Return the non-negative daily runtime still available for automation."""
    budget = entry.runtime_data.coordinator.data.runtime_minutes
    delivered = entry.runtime_data.controller.delivered_today_seconds() / 60
    return round(max(0.0, budget - delivered), 3)


def _decision_reason(entry: SolarIrrigationConfigEntry) -> str:
    """Return a concise explanation of the current controller state."""
    controller = entry.runtime_data.controller
    data = entry.runtime_data.coordinator.data
    status = controller.state.status
    if status is ControllerStatus.IRRIGATING:
        return controller.state.decision_reason or "irrigation_pulse_running"
    if status is ControllerStatus.SOAKING:
        return "soil_soaking"
    if status is ControllerStatus.SLEEPING:
        return controller.state.decision_reason or "outside_watering_window"
    if status is ControllerStatus.RAIN_PAUSED:
        return controller.state.decision_reason or "rain_threshold_reached"
    if status is ControllerStatus.DAILY_BUDGET_REACHED:
        return "daily_budget_exhausted"
    if status is ControllerStatus.ERROR:
        return (
            controller.state.last_error
            or controller.state.decision_reason
            or "Controller error"
        )[:255]
    if status is ControllerStatus.WAITING_FOR_HISTORY:
        return "collecting_solar_history"
    if status is ControllerStatus.WAITING_FOR_PULSE:
        return controller.state.decision_reason or "waiting_for_water_demand"
    if controller.state.decision_reason and controller.state.decision_reason not in {
        "automatic_window_open",
        "cycle_completed",
        "controller_initialized",
    }:
        return controller.state.decision_reason
    if data.skip_reason is not None:
        return data.skip_reason
    if _remaining_budget(entry) <= 0:
        return "daily_budget_exhausted"
    return "ready_for_automatic_evaluation"


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return shared device information for all entities in one entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Solar Irrigation",
        model="Irrigation Manager",
    )
