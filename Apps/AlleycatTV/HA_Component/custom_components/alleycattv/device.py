"""Device helpers for AlleycatTV entity platforms."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info(pi_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, pi_id)},
        name=pi_id,
        manufacturer="Alleycat",
        model="TV Pi",
    )


def device_data(hass, pi_id: str) -> dict:
    return hass.data.get(DOMAIN, {}).get("devices", {}).get(pi_id, {})


def device_meta(hass, pi_id: str) -> dict:
    return hass.data.get(DOMAIN, {}).get("device_meta", {}).get(pi_id, {})
