"""URL normalization for Core Configurator service entries."""
from __future__ import annotations

from urllib.parse import urlparse

from .const import (
    EXTRA_ENABLED,
    EXTRA_LABEL,
    EXTRA_NODE,
    EXTRA_TOKEN,
    EXTRA_TOKEN_ID,
    EXTRA_TOKEN_SECRET,
    KEY_MASTER_CONTROL_SERVER,
    KEY_PROXMOX,
    KEY_RTSP,
    SERVICE_CATALOG,
    YAML_MCS_TOKEN,
    YAML_PROXMOX_TOKEN_ID,
    YAML_PROXMOX_TOKEN_SECRET,
    YAML_RTSP_ENABLED,
    YAML_RTSP_LABEL,
)


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
        elif key == KEY_RTSP:
            text = f"rtsp://{text}"
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


def _truthy(raw: object) -> str:
    """Normalize YAML/panel enabled values to ``\"true\"`` / ``\"false\"``."""
    if isinstance(raw, bool):
        return "true" if raw else "false"
    text = str(raw or "").strip().lower()
    if text in ("1", "true", "yes", "on"):
        return "true"
    return "false"


def empty_services() -> dict:
    """Return a services dict with empty URLs — no DEFAULTS. Callers fail closed."""
    out: dict = {}
    for spec in SERVICE_CATALOG:
        item: dict = {"url": "", "extra": {}}
        if spec["key"] == KEY_PROXMOX:
            item["extra"] = {EXTRA_NODE: "pve"}
        elif spec["key"] == KEY_RTSP:
            item["extra"] = {EXTRA_LABEL: "Live RTSP", EXTRA_ENABLED: "false"}
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
        services[KEY_PROXMOX].setdefault("extra", {})[EXTRA_NODE] = str(
            data.get("proxmox_node") or ""
        ).strip()
    if data.get(YAML_MCS_TOKEN) is not None:
        token = str(data.get(YAML_MCS_TOKEN) or "").strip()
        services[KEY_MASTER_CONTROL_SERVER].setdefault("extra", {})[EXTRA_TOKEN] = token
    if data.get(YAML_PROXMOX_TOKEN_ID) is not None:
        services[KEY_PROXMOX].setdefault("extra", {})[EXTRA_TOKEN_ID] = str(
            data.get(YAML_PROXMOX_TOKEN_ID) or ""
        ).strip()
    if data.get(YAML_PROXMOX_TOKEN_SECRET) is not None:
        services[KEY_PROXMOX].setdefault("extra", {})[EXTRA_TOKEN_SECRET] = str(
            data.get(YAML_PROXMOX_TOKEN_SECRET) or ""
        ).strip()
    if data.get(YAML_RTSP_LABEL) is not None:
        label = str(data.get(YAML_RTSP_LABEL) or "").strip() or "Live RTSP"
        services[KEY_RTSP].setdefault("extra", {})[EXTRA_LABEL] = label
    if data.get(YAML_RTSP_ENABLED) is not None:
        services[KEY_RTSP].setdefault("extra", {})[EXTRA_ENABLED] = _truthy(
            data.get(YAML_RTSP_ENABLED)
        )
    return services
