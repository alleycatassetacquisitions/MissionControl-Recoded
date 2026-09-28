"""Config flow for Bug Buster — no tokens (Core Configurator owns those)."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MQTT_TOPIC,
    CONF_VERIFY_SSL,
    DEFAULT_MQTT_TOPIC,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)


class BugBusterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            return self.async_create_entry(title="Bug Buster", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                    vol.Optional(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): str,
                }
            ),
        )

    async def async_step_import(self, user_input: dict | None = None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        data = user_input or {}
        await self.async_set_unique_id(DOMAIN)
        return self.async_create_entry(
            title="Bug Buster",
            data={
                CONF_VERIFY_SSL: bool(data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)),
                CONF_MQTT_TOPIC: data.get(CONF_MQTT_TOPIC) or DEFAULT_MQTT_TOPIC,
            },
        )
