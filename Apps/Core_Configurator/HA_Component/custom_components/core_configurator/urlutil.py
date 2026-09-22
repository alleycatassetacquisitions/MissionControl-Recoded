"""URL normalization for Core Configurator service entries."""
from __future__ import annotations

from urllib.parse import urlparse

from .const import KEY_PROXMOX, SERVICE_CATALOG


def normalize_url(raw: str, *, key: str = "") -> str:
    """Normalize a URL from user input. Returns empty string for blank input."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        if key == KEY_PROXMOX:
            if ":" not in text.split("/")[0]:
                text = f"{text}:8006"
            text = f"https://{text}"
        else:
            text = f"http://{text}"
    parsed = urlparse(text)
    if not parsed.hostname:
        return text.rstrip("/")
    if key == KEY_PROXMOX and parsed.port is None:
        host = parsed.hostname
        netloc = f"[{host}]:8006" if ":" in host else f"{host}:8006"
        return f"{parsed.scheme}://{netloc}"
    return text.rstrip("/")


def empty_services() -> dict:
    """Return a services dict with empty URLs — no DEFAULTS. Callers fail closed."""
    out: dict = {}
    for spec in SERVICE_CATALOG:
        item: dict = {"url": "", "extra": {}}
        if spec["key"] == KEY_PROXMOX:
            item["extra"] = {"node": "pve"}
        out[spec["key"]] = item
    return out


def services_from_mapping(data: dict) -> dict:
    """Build the stored services dict from YAML / config-flow fields."""
    services = empty_services()
    for spec in SERVICE_CATALOG:
        key = spec["key"]
        if data.get(key):
            services[key]["url"] = normalize_url(str(data[key]), key=key)
    if data.get("proxmox_node") is not None:
        services[KEY_PROXMOX].setdefault("extra", {})["node"] = str(
            data.get("proxmox_node") or ""
        ).strip()
    return services
