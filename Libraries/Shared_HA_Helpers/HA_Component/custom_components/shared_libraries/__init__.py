"""Shared HA Helpers — infrastructure for Mission Control integrations.

This is not an operator-facing app. It has no sidebar, no config flow,
and no UI. Other integrations declare it as a manifest dependency and
import helpers directly:

    from custom_components.shared_libraries.http import async_request
    from custom_components.shared_libraries.mqtt import mc_topic, async_subscribe
    from custom_components.shared_libraries.fabric import async_start_presence_tracking

Design principles applied:
  P8  Reusable primitive — HTTP and MQTT helpers live here, not copied per app.
  P2  Prefer authority over consensus — Core Configurator is the URL authority;
      async_request calls get_url rather than accepting a raw URL from callers.
  P6  Remove root causes — no app-local aiohttp sessions or private MQTT clients.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Shared HA Helpers component.

    No configuration is accepted. The domain is registered in hass.data so
    callers can confirm the component is loaded if needed.
    """
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("Shared HA Helpers loaded")
    return True
