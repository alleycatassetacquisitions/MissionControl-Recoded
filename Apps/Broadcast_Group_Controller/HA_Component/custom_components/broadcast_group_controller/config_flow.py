"""Install-only config flow for Broadcast Group Controller."""
from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN


class BroadcastGroupControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single install-only entry — no options."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Broadcast Group Controller", data={})
        return self.async_show_form(step_id="user")

    async def async_step_import(self, user_input=None):
        return await self.async_step_user(user_input or {})
