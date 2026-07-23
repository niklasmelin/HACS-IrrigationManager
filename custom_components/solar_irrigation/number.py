"""Writable tuning entities for the Solar Irrigation integration.

The number platform deliberately exposes only parameters that are expected to
change during normal operation. Fixed installation calibration, such as peak
solar production, remains in the config entry options.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarIrrigationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the seasonal water-demand control for one config entry."""
    del hass
    async_add_entities([PeakDailyWaterDemandNumber(entry)])


class PeakDailyWaterDemandNumber(NumberEntity):
    """Adjust the peak-day irrigation runtime used to scale daily demand.

    The value is expressed as total pump-on minutes per local calendar day. It
    is both a crop-season calibration and the hard upper bound for automatic
    irrigation. Changing it updates config-entry options, persists the value,
    reloads the entry, and therefore recalculates the current daily budget.
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
            self.entry.options.get(
                CONF_PEAK_DAILY_WATER_DEMAND,
                self.entry.data.get(
                    CONF_PEAK_DAILY_WATER_DEMAND,
                    DEFAULT_PEAK_DAILY_WATER_DEMAND,
                ),
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Persist a new seasonal demand value and reload the integration.

        Home Assistant validates the range before calling this method. The
        explicit clamp protects direct/internal calls and preserves the stated
        10-240 minute contract.
        """
        value = max(
            MIN_PEAK_DAILY_WATER_DEMAND,
            min(MAX_PEAK_DAILY_WATER_DEMAND, float(value)),
        )
        options = dict(self.entry.options)
        options[CONF_PEAK_DAILY_WATER_DEMAND] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
