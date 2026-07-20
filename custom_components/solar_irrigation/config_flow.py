"""Config flow for Solar Irrigation integration."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_SOLAR_SENSOR,
    CONF_REMAINING_SENSOR,
    CONF_IRRIGATION_ENTITY,
    CONF_MAX_SOLAR,
    CONF_MAX_RUNTIME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MAX_SOLAR,
    DEFAULT_MAX_RUNTIME,
    DEFAULT_UPDATE_INTERVAL,
)

class SolarIrrigationConfigFlow(config_entries.ConfigFlow, domain="solar_irrigation"):
    """Handle a config flow for Solar Irrigation."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="Solar Irrigation", data=user_input)

        # Define the configuration schema with proper entity selectors
        data_schema = vol.Schema({
            vol.Required(CONF_SOLAR_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_REMAINING_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_IRRIGATION_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Optional(CONF_MAX_SOLAR, default=DEFAULT_MAX_SOLAR): vol.All(
                vol.Coerce(float), vol.Range(min=0)
            ),
            vol.Optional(CONF_MAX_RUNTIME, default=DEFAULT_MAX_RUNTIME): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
            vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema
        )