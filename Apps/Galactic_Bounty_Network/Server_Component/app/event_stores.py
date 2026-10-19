"""Per-event PosterStore cache + legacy global store."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Optional

from app.services.event_paths import ensure_event_dirs, event_posters_file, sanitize_event_id
from app.store import PosterStore


class EventPosterStores:
    """Lazy PosterStore instances keyed by event_id."""

    def __init__(self, legacy_path: Path) -> None:
        self._legacy = PosterStore(legacy_path)
        self._by_event: Dict[str, PosterStore] = {}
        self._lock = threading.Lock()

    @property
    def legacy(self) -> PosterStore:
        return self._legacy

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
        """Prefer active-event store, then legacy global posters.json."""
        if event_id:
            try:
                poster = self.for_event(event_id).get_by_player(player_id)
                if poster:
                    return poster, event_id
            except ValueError:
                pass
        poster = self._legacy.get_by_player(player_id)
        if poster:
            return poster, None
        return None, None
