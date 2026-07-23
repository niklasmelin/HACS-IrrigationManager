"""Writable seasonal tuning entities for Solar Irrigation."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_PEAK_DAILY_WATER_DEMAND,
    DEFAULT_PEAK_DAILY_WATER_DEMAND,
    DOMAIN,
    MAX_PEAK_DAILY_WATER_DEMAND,
    MIN_PEAK_DAILY_WATER_DEMAND,
)
from .models import SolarIrrigationConfigEntry
from .watering_window import entry_value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the seasonal water-demand control for one config entry."""
    del hass
    async_add_entities([PeakDailyWaterDemandNumber(entry)])


class PeakDailyWaterDemandNumber(NumberEntity):
    """Adjust peak-day pump-on minutes used to scale the daily water budget.

    The value is a seasonal crop-demand calibration and the hard automatic daily
    limit before solar and rain factors are applied. It is stored in config-entry
    options. Updating the number refreshes the calculation in place so an active
    pulse-and-soak event is not interrupted; the event rechecks the new budget
    before its next automatic pulse.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "peak_daily_water_demand"
    _attr_native_min_value = MIN_PEAK_DAILY_WATER_DEMAND
    _attr_native_max_value = MAX_PEAK_DAILY_WATER_DEMAND
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:water-percent"

    def __init__(self, entry: SolarIrrigationConfigEntry) -> None:
        """Initialize a stable entity linked to the owning config entry."""
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_peak_daily_water_demand"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Solar Irrigation",
            model="Irrigation Manager",
        )

    @property
    def native_value(self) -> float:
        """Return the effective persisted peak daily demand in minutes."""
        return float(
            entry_value(
                self.entry,
                CONF_PEAK_DAILY_WATER_DEMAND,
                DEFAULT_PEAK_DAILY_WATER_DEMAND,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Persist a clamped value and refresh calculations without a reload."""
        value = max(
            MIN_PEAK_DAILY_WATER_DEMAND,
            min(MAX_PEAK_DAILY_WATER_DEMAND, float(value)),
        )
        runtime = self.entry.runtime_data
        runtime.suppress_next_reload = True
        options = dict(self.entry.options)
        options[CONF_PEAK_DAILY_WATER_DEMAND] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        await runtime.coordinator.async_request_refresh()
        self.async_write_ha_state()
