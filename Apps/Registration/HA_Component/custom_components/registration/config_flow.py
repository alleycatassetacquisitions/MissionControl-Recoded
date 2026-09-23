"""Config flow for Registration.

One setup step: enter the MCS API token. The MCS URL comes from Core
Configurator — operators set it there, not here. Tokens are credentials;
they live in the config entry, never in Core Configurator.

Registration is single-instance: only one entry allowed.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_MCS_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

_STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MCS_TOKEN): str,
    }
)


class RegistrationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for Registration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            token = user_input[CONF_MCS_TOKEN].strip()
            if not token:
                return self.async_show_form(
                    step_id="user",
                    data_schema=_STEP_SCHEMA,
                    errors={"mcs_token": "token_required"},
                )
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Registration",
                data={CONF_MCS_TOKEN: token},
            )

        return self.async_show_form(step_id="user", data_schema=_STEP_SCHEMA)
