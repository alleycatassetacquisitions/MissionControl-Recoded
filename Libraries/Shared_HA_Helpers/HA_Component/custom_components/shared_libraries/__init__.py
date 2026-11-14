"""Shared HA Helpers — HTTP client and MQTT fabric primitives for Mission Control integrations.

No sidebar, no config flow. Other integrations import from http, mqtt, and fabric directly.
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
