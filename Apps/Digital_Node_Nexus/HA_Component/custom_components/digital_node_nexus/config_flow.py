"""Config flow for Digital Node Nexus.

Install-only: creates a single config entry with no credentials.
MCS URL/token come from Core Configurator. MQTT uses HA's mqtt integration.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class DigitalNodeNexusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for Digital Node Nexus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Digital Node Nexus", data={})

        return self.async_show_form(step_id="user")
