"""One-shot bootstrap of HA Core Proxmox VE from Core Configurator credentials.

CC owns the Proxmox URL/token. Monitoring entities live in Core ``proxmoxve``.
Create that entry once when credentials are complete; skip if a matching host
entry already exists. Does not rotate secrets on an existing entry.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .const import (
    DOMAIN,
    EXTRA_TOKEN_ID,
    EXTRA_TOKEN_SECRET,
    KEY_PROXMOX,
)
from .helpers import get_extra, get_url

_LOGGER = logging.getLogger(__name__)

PROXMOXVE_DOMAIN = "proxmoxve"

_PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "replace-me",
        "changeme",
        "change-me",
        "your-token-here",
        "secret",
        "replace-with-proxmox-token-secret",
    }
)


def parse_proxmox_token_id(full_id: str) -> tuple[str, str, str] | None:
    """Split ``user@realm!token_name`` into (user, realm, token_name)."""
    text = (full_id or "").strip()
    if "!" not in text or "@" not in text.split("!", 1)[0]:
        return None
    user_realm, token_name = text.split("!", 1)
    username, _, realm = user_realm.partition("@")
    username = username.strip()
    realm = realm.strip().lower()
    token_name = token_name.strip()
    if not username or not realm or not token_name:
        return None
    return username, realm, token_name


def parse_proxmox_host_port(url: str) -> tuple[str, int] | None:
    """Return (host, port) from a Proxmox base URL."""
    text = (url or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlparse(text)
    host = parsed.hostname
    if not host:
        return None
    return host, int(parsed.port or 8006)


def _existing_host_entry(hass: HomeAssistant, host: str):
    host_l = host.lower()
    for entry in hass.config_entries.async_entries(PROXMOXVE_DOMAIN):
        if str(entry.data.get("host") or "").lower() == host_l:
            return entry
    return None


def _cc_credentials(hass: HomeAssistant) -> dict[str, Any] | None:
    url = get_url(hass, KEY_PROXMOX)
    token_id = get_extra(hass, KEY_PROXMOX, EXTRA_TOKEN_ID)
    token_secret = get_extra(hass, KEY_PROXMOX, EXTRA_TOKEN_SECRET)
    if not url or not token_id or not token_secret:
        return None
    if token_secret.strip().lower() in _PLACEHOLDER_SECRETS:
        return None
    parsed_token = parse_proxmox_token_id(token_id)
    if parsed_token is None:
        _LOGGER.warning(
            "Core Configurator: Proxmox token_id must be user@realm!name "
            "(got %r); skipping Proxmox VE bootstrap",
            token_id,
        )
        return None
    host_port = parse_proxmox_host_port(url)
    if host_port is None:
        return None
    username, realm, token_name = parsed_token
    host, port = host_port
    # Core proxmoxve expects short token name; full id breaks some Core builds.
    return {
        "host": host,
        "port": port,
        "username": username,
        "auth_method": realm if realm in ("pam", "pve") else "other",
        "realm": realm,
        "token": True,
        "verify_ssl": False,
        "token_id": token_name,
        "token_value": token_secret.strip(),
    }


def _schema_keys(schema: Any) -> set[str]:
    keys: set[str] = set()
    if schema is None:
        return keys
    try:
        for marker in schema.schema:
            underlying = getattr(marker, "schema", marker)
            keys.add(str(underlying))
    except Exception:  # noqa: BLE001
        return set()
    return keys


def _token_flow_supported() -> bool:
    """True when Core proxmoxve ships API-token config (HA 2026.3+)."""
    try:
        from homeassistant.components.proxmoxve.const import (  # noqa: F401
            CONF_TOKEN_ID,
        )
    except ImportError:
        return False
    return True


async def _finish_user_flow(hass: HomeAssistant, creds: dict[str, Any]) -> dict[str, str]:
    if not _token_flow_supported():
        return {
            "status": "unsupported",
            "detail": "HA Core Proxmox VE lacks API-token config flow "
            "(need Home Assistant 2026.3+)",
        }

    result = await hass.config_entries.flow.async_init(
        PROXMOXVE_DOMAIN, context={"source": SOURCE_USER}
    )
    if result.get("type") != FlowResultType.FORM:
        return {
            "status": "error",
            "detail": f"proxmoxve user flow unexpected: {result.get('type')} "
            f"{result.get('reason', '')}".strip(),
        }

    schema_keys = _schema_keys(result.get("data_schema"))
    step1 = {
        "host": creds["host"],
        "username": creds["username"],
        "port": creds["port"],
        "token": True,
        "verify_ssl": False,
    }
    if "auth_method" in schema_keys:
        step1["auth_method"] = creds["auth_method"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=step1
    )
    if result.get("type") == FlowResultType.CREATE_ENTRY:
        return {"status": "created", "detail": creds["host"]}
    if result.get("type") != FlowResultType.FORM:
        return {
            "status": "error",
            "detail": f"proxmoxve auth step unexpected: {result.get('type')} "
            f"{result.get('reason', '')}".strip(),
        }

    auth_input: dict[str, Any] = {
        "token_id": creds["token_id"],
        "token_value": creds["token_value"],
    }
    if creds["auth_method"] == "other":
        auth_input["realm"] = creds["realm"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=auth_input
    )
    if result.get("type") == FlowResultType.CREATE_ENTRY:
        return {"status": "created", "detail": creds["host"]}
    return {
        "status": "error",
        "detail": f"proxmoxve create failed: {result.get('type')} "
        f"{result.get('reason') or result.get('errors') or ''}".strip(),
    }


async def ensure_proxmoxve_entry(hass: HomeAssistant) -> dict[str, str]:
    """Create Core proxmoxve once from CC credentials. Idempotent per host."""
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("_proxmoxve_bootstrap_running"):
        return {"status": "busy", "detail": "bootstrap already running"}
    store["_proxmoxve_bootstrap_running"] = True
    try:
        creds = _cc_credentials(hass)
        if creds is None:
            return {"status": "skipped", "detail": "proxmox credentials incomplete"}

        existing = _existing_host_entry(hass, creds["host"])
        if existing is not None:
            return {
                "status": "exists",
                "detail": f"proxmoxve entry already present for {creds['host']}",
            }

        import_data = {
            "host": creds["host"],
            "port": creds["port"],
            "username": creds["username"],
            "auth_method": creds["auth_method"],
            "realm": creds["realm"],
            "token": True,
            "verify_ssl": False,
            "token_id": creds["token_id"],
            "token_value": creds["token_value"],
        }

        # 2026.4+ exposes SOURCE_IMPORT; newer Core may not — fall back to user flow.
        result = await hass.config_entries.flow.async_init(
            PROXMOXVE_DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=import_data,
        )
        rtype = result.get("type")
        reason = str(result.get("reason") or "")
        if rtype == FlowResultType.CREATE_ENTRY:
            _LOGGER.info(
                "Core Configurator: created Proxmox VE entry for %s", creds["host"]
            )
            return {"status": "created", "detail": creds["host"]}
        if rtype == FlowResultType.ABORT and reason not in (
            "not_supported",
            "unknown_source",
            "no_handler",
        ):
            if reason in ("already_configured",):
                return {
                    "status": "exists",
                    "detail": f"proxmoxve entry already present for {creds['host']}",
                }
            _LOGGER.warning(
                "Core Configurator: Proxmox VE import aborted (%s)", reason
            )
            return {"status": "error", "detail": f"import aborted: {reason}"}

        outcome = await _finish_user_flow(hass, creds)
        if outcome["status"] == "created":
            _LOGGER.info(
                "Core Configurator: created Proxmox VE entry for %s", creds["host"]
            )
        elif outcome["status"] == "unsupported":
            _LOGGER.warning("Core Configurator: %s", outcome["detail"])
        elif outcome["status"] == "error":
            _LOGGER.warning(
                "Core Configurator: Proxmox VE bootstrap failed: %s",
                outcome["detail"],
            )
        return outcome
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Core Configurator: Proxmox VE bootstrap failed: %s", err, exc_info=True
        )
        return {"status": "error", "detail": str(err)}
    finally:
        store["_proxmoxve_bootstrap_running"] = False


def schedule_proxmoxve_bootstrap(hass: HomeAssistant) -> None:
    """Fire-and-forget bootstrap; never blocks Core Configurator setup."""
    hass.async_create_task(ensure_proxmoxve_entry(hass))
