"""Event cache, persistent store, and GBN active-event push — owned by Game Master.

Moved from Registration in Phase 1c so event create / set-active authority
lives on Game Master only.  Registration reads active-event via
``registration/get_active_event`` (MCS-backed) and enriches names from this
cache via import.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    ACTIVE_EVENT_ID_KEY,
    DOMAIN,
    EVENT_CACHE_KEY,
    EVENT_STORE,
    KEY_GBN,
    KEY_MCS,
    EXTRA_MCS_TOKEN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory helpers
# ---------------------------------------------------------------------------


def event_cache(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    store = hass.data.setdefault(DOMAIN, {})
    return store.setdefault(EVENT_CACHE_KEY, {})


def cache_event(hass: HomeAssistant, event: dict[str, Any] | None) -> None:
    """Merge into session cache — never clobber a known name with a blank."""
    if not isinstance(event, dict):
        return
    event_id = event.get("id")
    if not event_id:
        return
    key = str(event_id)
    prev = event_cache(hass).get(key) or {}
    new_name = (event.get("name") or "").strip()
    new_created = (event.get("created_at") or "").strip()
    venue = event.get("venue_name")
    if venue is None and "venue_name" not in event:
        venue = prev.get("venue_name")
    event_cache(hass)[key] = {
        "id": key,
        "name": new_name or prev.get("name") or "",
        "venue_name": venue,
        "created_at": new_created or prev.get("created_at") or "",
    }


def enrich_active_from_cache(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Fill empty active-event name from session cache when MCS only has the id."""
    event_id = data.get("active_event_id")
    event = data.get("event")
    if not event_id:
        # Fall back to HA-persisted active when MCS memory was wiped
        event_id = hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY)
        if event_id:
            data = {**data, "active_event_id": event_id}
    if not event_id:
        return data
    cached = event_cache(hass).get(str(event_id))
    if not cached:
        return data
    if not isinstance(event, dict):
        event = {
            "id": str(event_id),
            "name": "",
            "venue_name": None,
            "created_at": "",
        }
    if not (event.get("name") or "").strip() and cached.get("name"):
        event = {**event, "name": cached["name"]}
    if event.get("venue_name") is None and cached.get("venue_name") is not None:
        event = {**event, "venue_name": cached.get("venue_name")}
    if not (event.get("id") or "").strip():
        event = {**event, "id": str(event_id)}
    return {**data, "event": event, "active_event_id": str(event_id)}


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


async def save_event_store(hass: HomeAssistant) -> None:
    """Persist known events + active id so names survive HA restart."""
    store: Store | None = hass.data.get(DOMAIN, {}).get(EVENT_STORE)
    if store is None:
        return
    await store.async_save(
        {
            "events": dict(event_cache(hass)),
            "active_event_id": hass.data[DOMAIN].get(ACTIVE_EVENT_ID_KEY),
        }
    )


async def load_event_store(hass: HomeAssistant) -> None:
    """Load persisted events into memory (until Central GET /events is ready)."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    hass.data.setdefault(DOMAIN, {})[EVENT_STORE] = store
    data = await store.async_load() or {}
    for item in (data.get("events") or {}).values():
        if isinstance(item, dict):
            cache_event(hass, item)
    active_id = data.get("active_event_id")
    if active_id:
        hass.data[DOMAIN][ACTIVE_EVENT_ID_KEY] = str(active_id)


async def remember_active(hass: HomeAssistant, event_id: str | None) -> None:
    hass.data.setdefault(DOMAIN, {})[ACTIVE_EVENT_ID_KEY] = event_id
    await save_event_store(hass)


# ---------------------------------------------------------------------------
# GBN + MCS restore helpers
# ---------------------------------------------------------------------------


async def push_active_event_to_gbn(
    hass: HomeAssistant, event_id: str, event_name: str = ""
) -> None:
    """Tell GBN the active event so /poster-cycle kiosks do not wait on MCS."""
    try:
        from custom_components.shared_libraries.http import async_request
    except ImportError:
        _LOGGER.debug("Game Master: shared_libraries not available — GBN push skipped")
        return
    if not event_id:
        return
    name = (event_name or "").strip()
    if not name:
        cached = event_cache(hass).get(str(event_id)) or {}
        name = str(cached.get("name") or "").strip()
    try:
        response = await async_request(
            hass,
            KEY_GBN,
            "PUT",
            "/api/events/active",
            json={
                "active_event_id": str(event_id),
                "event_name": name,
            },
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Game Master: GBN active-event push failed: %s", err)
        return
    if response is None:
        _LOGGER.debug("Game Master: GBN URL not configured — skip active push")
        return
    try:
        if response.status >= 400:
            _LOGGER.warning(
                "Game Master: GBN active-event push HTTP %s",
                response.status,
            )
        else:
            _LOGGER.info(
                "Game Master: pushed active event %s (%s) to GBN",
                event_id,
                name or "unnamed",
            )
    finally:
        response.release()


async def restore_active_to_mcs(hass: HomeAssistant) -> None:
    """After HA/MCS restart, re-apply last active + name hint to MCS memory."""
    event_id = hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY)
    if not event_id:
        return
    cached = event_cache(hass).get(str(event_id)) or {}
    memory: dict[str, Any] = {}
    if cached.get("name"):
        memory["name"] = cached["name"]
    if cached.get("venue_name") is not None:
        memory["venue_name"] = cached["venue_name"]

    try:
        from custom_components.shared_libraries.http import async_request
    except ImportError:
        _LOGGER.warning(
            "Game Master: shared_libraries not available — cannot restore active event"
        )
        return
    try:
        from custom_components.core_configurator.helpers import get_extra

        token = str(get_extra(hass, KEY_MCS, EXTRA_MCS_TOKEN, "") or "")
    except ImportError:
        _LOGGER.warning(
            "Game Master: core_configurator not available — cannot restore active event"
        )
        return
    if not token:
        _LOGGER.warning(
            "Game Master: MCS token not set — cannot restore active event to MCS"
        )
        return

    try:
        response = await async_request(
            hass,
            KEY_MCS,
            "PUT",
            f"/events/{event_id}/active",
            token=token,
            json=memory or None,
        )
        if response is None:
            _LOGGER.warning(
                "Game Master: MCS unreachable — could not restore active event"
            )
        elif response.status >= 400:
            _LOGGER.warning(
                "Game Master: could not restore active event to MCS (HTTP %s)",
                response.status,
            )
        else:
            _LOGGER.info(
                "Game Master: restored active event %s (%s) to MCS memory",
                event_id,
                cached.get("name") or "unnamed",
            )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Game Master: could not restore active event to MCS: %s", err
        )

    await push_active_event_to_gbn(
        hass, str(event_id), str(cached.get("name") or "")
    )
