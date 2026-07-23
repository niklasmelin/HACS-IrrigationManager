"""Writable runtime tuning entities for Solar Irrigation."""

from __future__ import annotations

from typing import Final

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_MAX_PULSE_DURATION,
    CONF_PEAK_DAILY_WATER_DEMAND,
    CONF_SOAK_DURATION,
    DEFAULT_MAX_PULSE_DURATION,
    DEFAULT_PEAK_DAILY_WATER_DEMAND,
    DEFAULT_SOAK_DURATION,
    DOMAIN,
    MAX_MAX_PULSE_DURATION,
    MAX_PEAK_DAILY_WATER_DEMAND,
    MAX_SOAK_DURATION,
    MIN_MAX_PULSE_DURATION,
    MIN_PEAK_DAILY_WATER_DEMAND,
    MIN_SOAK_DURATION,
)
from .models import SolarIrrigationConfigEntry
from .watering_window import entry_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create writable runtime controls for one config entry."""
    del hass
    async_add_entities(
        [
            PeakDailyWaterDemandNumber(entry),
            MaximumPulseDurationNumber(entry),
            SoakDurationNumber(entry),
        ]
    )


class SolarIrrigationTuningNumber(NumberEntity):
    """Base class for persisted tuning values that update without a reload."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    config_key: str
    default_value: float
    minimum_value: float
    maximum_value: float
    unique_id_suffix: str

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize a stable entity linked to the owning config entry."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self.unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Solar Irrigation",
            model="Irrigation Manager",
        )

    @property
    def native_value(self) -> float:
        """Return the effective persisted tuning value in minutes."""
        value = float(entry_value(self.entry, self.config_key, self.default_value))
        return max(self.minimum_value, min(self.maximum_value, value))

    async def async_set_native_value(self, value: float) -> None:
        """Persist a clamped value and refresh calculations without a reload."""
        value = max(self.minimum_value, min(self.maximum_value, float(value)))
        runtime = self.entry.runtime_data
        runtime.suppress_next_reload = True
        options = dict(self.entry.options)
        options[self.config_key] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await runtime.coordinator.async_request_refresh()
        self.async_write_ha_state()


class PeakDailyWaterDemandNumber(SolarIrrigationTuningNumber):
    """Adjust peak-day pump-on minutes used to scale the daily water budget.

    The value is the seasonal crop-demand calibration and the hard automatic
    daily limit before solar and rain factors are applied. Updating it refreshes
    calculations in place. An active pulse is not interrupted, but the event
    rechecks the resulting budget before its next automatic pulse.
    """

    _attr_translation_key = "peak_daily_water_demand"
    _attr_native_min_value = MIN_PEAK_DAILY_WATER_DEMAND
    _attr_native_max_value = MAX_PEAK_DAILY_WATER_DEMAND
    _attr_native_step = 1.0
    _attr_icon = "mdi:water-percent"

    config_key: Final = CONF_PEAK_DAILY_WATER_DEMAND
    default_value: Final = DEFAULT_PEAK_DAILY_WATER_DEMAND
    minimum_value: Final = MIN_PEAK_DAILY_WATER_DEMAND
    maximum_value: Final = MAX_PEAK_DAILY_WATER_DEMAND
    unique_id_suffix: Final = "peak_daily_water_demand"


class MaximumPulseDurationNumber(SolarIrrigationTuningNumber):
    """Adjust the maximum pump-on duration of each watering pulse.

    A running pulse keeps the duration selected when it started. The updated
    value is used when the controller plans the next pulse in the active event,
    or the first pulse of the next event.
    """

    _attr_translation_key = "maximum_pulse_duration"
    _attr_native_min_value = MIN_MAX_PULSE_DURATION
    _attr_native_max_value = MAX_MAX_PULSE_DURATION
    _attr_native_step = 0.5
    _attr_icon = "mdi:timer-play-outline"

    config_key: Final = CONF_MAX_PULSE_DURATION
    default_value: Final = DEFAULT_MAX_PULSE_DURATION
    minimum_value: Final = MIN_MAX_PULSE_DURATION
    maximum_value: Final = MAX_MAX_PULSE_DURATION
    unique_id_suffix: Final = "maximum_pulse_duration"


class SoakDurationNumber(SolarIrrigationTuningNumber):
    """Adjust the pump-off soak duration between watering pulses.

    A soak already in progress keeps its scheduled deadline. The updated value
    is used for the next soak period created by the active or next event.
    """

    _attr_translation_key = "soak_duration"
    _attr_native_min_value = MIN_SOAK_DURATION
    _attr_native_max_value = MAX_SOAK_DURATION
    _attr_native_step = 1.0
    _attr_icon = "mdi:timer-sand"

    config_key: Final = CONF_SOAK_DURATION
    default_value: Final = DEFAULT_SOAK_DURATION
    minimum_value: Final = MIN_SOAK_DURATION
    maximum_value: Final = MAX_SOAK_DURATION
    unique_id_suffix: Final = "soak_duration"
