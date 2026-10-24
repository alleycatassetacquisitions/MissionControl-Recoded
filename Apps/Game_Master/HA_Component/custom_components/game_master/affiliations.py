"""Event-keyed affiliation catalog cache — owned by Game Master."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import AFFILIATION_CATALOG_KEY, DOMAIN, EXTRA_MCS_TOKEN, KEY_MCS

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
