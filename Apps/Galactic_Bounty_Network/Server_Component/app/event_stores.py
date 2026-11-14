"""Per-event PosterStore cache (active-event only — D17 dropped legacy store)."""
from __future__ import annotations

import threading
from typing import Dict, Optional

from app.services.event_paths import ensure_event_dirs, event_posters_file, sanitize_event_id
from app.store import PosterStore


class EventPosterStores:
    """Lazy PosterStore instances keyed by event_id."""

    def __init__(self) -> None:
        self._by_event: Dict[str, PosterStore] = {}
        self._lock = threading.Lock()

    def for_event(self, event_id: str) -> PosterStore:
        eid = sanitize_event_id(event_id)
        with self._lock:
            store = self._by_event.get(eid)
            if store is None:
                ensure_event_dirs(eid)
                store = PosterStore(event_posters_file(eid))
                self._by_event[eid] = store
            return store

    def drop_cached(self, event_id: str) -> None:
        try:
            eid = sanitize_event_id(event_id)
        except ValueError:
            return
        with self._lock:
            self._by_event.pop(eid, None)

    def get_poster_for_player(
        self, player_id: str, event_id: Optional[str] = None
    ):
        """Resolve poster from the active/event store only."""
        if not event_id:
            return None, None
        try:
            poster = self.for_event(event_id).get_by_player(player_id)
            if poster:
                return poster, event_id
        except ValueError:
            pass
        return None, None
