"""Event-keyed affiliation catalog cache — owned by Game Master.

Also persists HA-only per-category default affiliation ids (never sent to
Central). Defaults prefill Registration's create-player form only.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import (
    AFFILIATION_CATALOG_KEY,
    AFFILIATION_DEFAULTS_KEY,
    AFFILIATION_DEFAULTS_STORE,
    AFFILIATION_DEFAULTS_VERSION,
    DOMAIN,
    EXTRA_MCS_TOKEN,
    KEY_MCS,
)

_LOGGER = logging.getLogger(__name__)


def _mcs_token(hass: HomeAssistant) -> str:
    try:
        from custom_components.core_configurator.helpers import get_extra

        return str(get_extra(hass, KEY_MCS, EXTRA_MCS_TOKEN, "") or "")
    except Exception:  # noqa: BLE001
        return ""


def catalog_store(hass: HomeAssistant) -> dict[str, Any]:
    store = hass.data.setdefault(DOMAIN, {})
    return store.setdefault(
        AFFILIATION_CATALOG_KEY,
        {"event_id": None, "categories": []},
    )


def clear_catalog(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    store[AFFILIATION_CATALOG_KEY] = {"event_id": None, "categories": []}


def defaults_memory(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """In-memory map: event_id → {category_id → affiliation_id}."""
    store = hass.data.setdefault(DOMAIN, {})
    return store.setdefault(AFFILIATION_DEFAULTS_KEY, {})


def enrich_catalog_with_defaults(
    catalog: dict[str, Any],
    defaults_by_event: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Attach default_affiliation_id onto each category (HA-only field).

    Pure helper — safe to unit-test without Home Assistant.
    """
    eid = str(catalog.get("event_id") or "").strip()
    event_defaults = defaults_by_event.get(eid, {}) if eid else {}
    categories: list[dict[str, Any]] = []
    for cat in catalog.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        cat_id = str(cat.get("id") or "")
        choice_ids = {
            str(a.get("id"))
            for a in (cat.get("affiliations") or [])
            if isinstance(a, dict) and a.get("id")
        }
        default_id = str(event_defaults.get(cat_id) or "").strip()
        if default_id and default_id not in choice_ids:
            default_id = ""
        categories.append(
            {
                **cat,
                "default_affiliation_id": default_id or None,
            }
        )
    return {
        "event_id": catalog.get("event_id"),
        "categories": categories,
    }


async def async_load_defaults(hass: HomeAssistant) -> None:
    """Load persisted defaults into hass.data."""
    store = Store(hass, AFFILIATION_DEFAULTS_VERSION, AFFILIATION_DEFAULTS_STORE)
    hass.data.setdefault(DOMAIN, {})["defaults_store"] = store
    raw = await store.async_load() or {}
    events = raw.get("events") if isinstance(raw, dict) else None
    memory: dict[str, dict[str, str]] = {}
    if isinstance(events, dict):
        for eid, cats in events.items():
            if not isinstance(cats, dict):
                continue
            cleaned: dict[str, str] = {}
            for cat_id, aff_id in cats.items():
                cid = str(cat_id or "").strip()
                aid = str(aff_id or "").strip()
                if cid and aid:
                    cleaned[cid] = aid
            if cleaned:
                memory[str(eid)] = cleaned
    hass.data[DOMAIN][AFFILIATION_DEFAULTS_KEY] = memory


async def async_save_defaults(hass: HomeAssistant) -> None:
    store = hass.data.get(DOMAIN, {}).get("defaults_store")
    if store is None:
        store = Store(
            hass, AFFILIATION_DEFAULTS_VERSION, AFFILIATION_DEFAULTS_STORE
        )
        hass.data.setdefault(DOMAIN, {})["defaults_store"] = store
    memory = defaults_memory(hass)
    await store.async_save({"events": memory})


async def set_default_affiliation(
    hass: HomeAssistant,
    *,
    category_id: str,
    affiliation_id: str,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Set or clear the HA-only default for a category on the active event.

    Pass empty affiliation_id to clear. Returns the enriched catalog.
    """
    eid = (event_id or "").strip() or await resolve_active_event_id(hass)
    if not eid:
        raise ValueError("No active event — set one in Registration first.")
    cat_id = str(category_id or "").strip()
    if not cat_id:
        raise ValueError("category_id is required")
    aff_id = str(affiliation_id or "").strip()

    memory = defaults_memory(hass)
    event_map = dict(memory.get(eid) or {})
    if aff_id:
        event_map[cat_id] = aff_id
    else:
        event_map.pop(cat_id, None)
    if event_map:
        memory[eid] = event_map
    else:
        memory.pop(eid, None)
    await async_save_defaults(hass)
    catalog = await refresh_catalog(hass, event_id=eid)
    return enrich_catalog_with_defaults(catalog, defaults_memory(hass))


async def resolve_active_event_id(hass: HomeAssistant) -> str:
    token = _mcs_token(hass)
    if async_request is None or not token:
        return ""
    response = await async_request(
        hass, KEY_MCS, "GET", "/events/active", token=token
    )
    if response is None or response.status >= 400:
        return ""
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(data, dict):
        return str(data.get("active_event_id") or "")
    return ""


async def refresh_catalog(
    hass: HomeAssistant, *, event_id: str | None = None
) -> dict[str, Any]:
    """Fetch categories + choices for the active event; store event-keyed cache."""
    eid = (event_id or "").strip() or await resolve_active_event_id(hass)
    cache = catalog_store(hass)
    if not eid:
        clear_catalog(hass)
        return catalog_store(hass)
    if cache.get("event_id") and str(cache.get("event_id")) != eid:
        clear_catalog(hass)

    empty: dict[str, Any] = {"event_id": eid, "categories": []}
    if async_request is None:
        hass.data[DOMAIN][AFFILIATION_CATALOG_KEY] = empty
        return empty
    token = _mcs_token(hass)
    if not token:
        hass.data[DOMAIN][AFFILIATION_CATALOG_KEY] = empty
        return empty

    cats_resp = await async_request(
        hass, KEY_MCS, "GET", "/affiliation-categories", token=token
    )
    if cats_resp is None or cats_resp.status >= 400:
        if str(cache.get("event_id") or "") == eid:
            return cache
        hass.data[DOMAIN][AFFILIATION_CATALOG_KEY] = empty
        return empty
    try:
        cats_raw = await cats_resp.json()
    except Exception:  # noqa: BLE001
        hass.data[DOMAIN][AFFILIATION_CATALOG_KEY] = empty
        return empty
    if not isinstance(cats_raw, list):
        cats_raw = []

    categories: list[dict[str, Any]] = []
    for cat in cats_raw:
        if not isinstance(cat, dict) or not cat.get("id"):
            continue
        cat_id = str(cat["id"])
        choices: list[dict[str, Any]] = []
        aff_resp = await async_request(
            hass,
            KEY_MCS,
            "GET",
            f"/affiliation-categories/{cat_id}/affiliations",
            token=token,
        )
        if aff_resp is not None and aff_resp.status < 400:
            try:
                aff_raw = await aff_resp.json()
            except Exception:  # noqa: BLE001
                aff_raw = []
            if isinstance(aff_raw, list):
                for aff in aff_raw:
                    if isinstance(aff, dict) and aff.get("id"):
                        choices.append(
                            {
                                "id": str(aff["id"]),
                                "name": str(aff.get("name") or ""),
                            }
                        )
        categories.append(
            {
                "id": cat_id,
                "name": str(cat.get("name") or ""),
                "affiliations": choices,
            }
        )

    result = {"event_id": eid, "categories": categories}
    hass.data[DOMAIN][AFFILIATION_CATALOG_KEY] = result
    return result


async def get_enriched_catalog(hass: HomeAssistant) -> dict[str, Any]:
    """Refresh (if needed) and return catalog with HA defaults attached."""
    catalog = await refresh_catalog(hass)
    return enrich_catalog_with_defaults(catalog, defaults_memory(hass))
