"""Lookup helpers for Core Configurator.

Other integrations use this as the authority for service URLs.
get_url is fail-closed: returns empty string when no URL is stored.
Do not call DEFAULTS or fall back to a hardcoded IP.
"""
from __future__ import annotations

from typing import Any

from .const import DOMAIN, EVENT_UPDATED, SERVICE_CATALOG


def get_services(hass) -> dict[str, dict[str, Any]]:
    data = hass.data.get(DOMAIN) or {}
    return dict(data.get("services") or {})


def get_url(hass, key: str, default: str = "") -> str:
    """Return the stored URL for key, or default (empty by design — fail closed)."""
    services = get_services(hass)
    url = str((services.get(key) or {}).get("url") or "").strip().rstrip("/")
    return url if url else str(default).rstrip("/")


def get_extra(hass, key: str, field: str, default: str = "") -> str:
    """Return one extra field for key (e.g. Proxmox node name)."""
    services = get_services(hass)
    extra = (services.get(key) or {}).get("extra") or {}
    value = extra.get(field)
    if value is None or value == "":
        return default
    return str(value)


def catalog_public(hass) -> list[dict[str, Any]]:
    """Return the full catalog safe to send to the frontend."""
    stored = get_services(hass)
    out = []
    for spec in SERVICE_CATALOG:
        item = dict(spec)
        extra_fields = item.pop("extra_fields", ())
        saved = stored.get(spec["key"]) or {}
        item["url"] = str(saved.get("url") or "").rstrip("/")
        item["extra"] = dict(saved.get("extra") or {})
        item["extra_fields"] = [dict(f) for f in extra_fields]
        out.append(item)
    return out


def save_services(
    hass,
    services: dict[str, dict[str, Any]],
    *,
    changed_key: str | None = None,
) -> None:
    """Write services to hass.data and persist to the config entry."""
    data = hass.data.setdefault(DOMAIN, {"services": {}, "entry_id": None})
    data["services"] = services
    entry_id = data.get("entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry:
            hass.config_entries.async_update_entry(entry, data={"services": services})
    hass.bus.async_fire(
        EVENT_UPDATED,
        {"key": changed_key, "services": catalog_public(hass)},
    )


def apply_service(
    hass,
    key: str,
    *,
    url: str | None = None,
    extra: dict | None = None,
) -> bool:
    """Write one service from another integration. No-op if Core Configurator is not set up."""
    if DOMAIN not in hass.data:
        return False
    from .urlutil import normalize_url

    services = get_services(hass)
    current = dict(services.get(key) or {"url": "", "extra": {}})
    if url is not None:
        current["url"] = normalize_url(str(url), key=key)
    if extra is not None:
        current["extra"] = {**dict(current.get("extra") or {}), **extra}
    services[key] = current
    save_services(hass, services, changed_key=key)
    return True
