"""Config flow for Core Configurator."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    KEY_ALLEYCATTV,
    KEY_GBN,
    KEY_PROXMOX,
    KEY_REGISTRATION_PRIMARY,
    KEY_REGISTRATION_SECONDARY,
    SERVICE_CATALOG,
)
from .urlutil import services_from_mapping


def _placeholder(key: str) -> str:
    for spec in SERVICE_CATALOG:
        if spec["key"] == key:
            return spec.get("placeholder", "")
    return ""


class CoreConfiguratorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow — runs once on first setup. Edit URLs from the sidebar later."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            return self.async_create_entry(
                title="Core Configurator",
                data={"services": services_from_mapping(user_input)},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        KEY_REGISTRATION_PRIMARY,
                        description={"suggested_value": _placeholder(KEY_REGISTRATION_PRIMARY)},
                    ): str,
                    vol.Optional(
                        KEY_REGISTRATION_SECONDARY,
                        description={"suggested_value": _placeholder(KEY_REGISTRATION_SECONDARY)},
                    ): str,
                    vol.Optional(
                        KEY_ALLEYCATTV,
                        description={"suggested_value": _placeholder(KEY_ALLEYCATTV)},
                    ): str,
                    vol.Optional(
                        KEY_GBN,
                        description={"suggested_value": _placeholder(KEY_GBN)},
                    ): str,
                    vol.Optional(
                        KEY_PROXMOX,
                        description={"suggested_value": _placeholder(KEY_PROXMOX)},
                    ): str,
                    vol.Optional(
                        "proxmox_node",
                        description={"suggested_value": "pve"},
                    ): str,
                }
            ),
        )

    async def async_step_import(self, user_input: dict | None = None) -> FlowResult:
        """Accept YAML seed on first boot. Ignored if the entry already exists."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        return self.async_create_entry(
            title="Core Configurator",
            data={"services": services_from_mapping(user_input or {})},
        )
