"""Playlist manager — fetches zone playlist and injects photos randomly."""
from __future__ import annotations

import json
import logging
import random
import threading
from typing import List, Optional, Tuple

import urllib.request
import urllib.parse

from config import (
    SERVER_URL, ZONE_ID, PHOTO_INTERVAL, PHOTO_DURATION, MEDIA_BASE_URL, CACHE_ENABLED
)

_LOGGER = logging.getLogger(__name__)


def _file_url(subdir: str, filename: str) -> str:
    return f"{MEDIA_BASE_URL}/{subdir}/{urllib.parse.quote(filename)}"


def _normalize_page_url(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


class PlaylistItem:
    """One entry in the playback queue.

    ``url`` is a dynamic property: it returns the local ``file://`` path when
    the file is fully cached, otherwise the original HTTP URL. This means
    player.py requires no changes — ``item.url`` always returns the best
    available source for mpv.
    """

    __slots__ = (
        "_url", "subdir", "filename",
        "is_photo", "is_webpage", "photo_duration",
        "webpage_duration", "display_name",
    )

    def __init__(
        self,
        url: str,
        subdir: str = "",
        filename: str = "",
        is_photo: bool = False,
        is_webpage: bool = False,
        photo_duration: int = 10,
        webpage_duration: int = 30,
        display_name: str = "",
    ):
        self._url = url
        self.subdir = subdir
        self.filename = filename
        self.is_photo = is_photo
        self.is_webpage = is_webpage
        self.photo_duration = photo_duration
        self.webpage_duration = webpage_duration
        self.display_name = display_name or url

    @property
    def url(self) -> str:
        """Return local file:// path if cached, else the original HTTP URL."""
        if CACHE_ENABLED and self.filename and self.subdir and not self.is_webpage:
            try:
                from cache_manager import get_cache_manager
                mgr = get_cache_manager()
                if mgr:
                    local = mgr.get_local_path(self.subdir, self.filename)
                    if local:
                        return f"file://{local}"
            except ImportError:
                pass
        return self._url

    @property
    def basename(self) -> str:
        if self.display_name:
            return self.display_name
        return self._url.rsplit("/", 1)[-1]

    def __repr__(self) -> str:
        kind = "photo" if self.is_photo else "webpage" if self.is_webpage else "video"
        return f"<PlaylistItem {kind} {self._url}>"


def _fetch_manifest() -> dict:
    """Fetch the server content manifest for cache freshness checks."""
    url = f"{SERVER_URL}/api/content/manifest"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        _LOGGER.debug("Could not fetch manifest (cache sync will use size-only check): %s", exc)
        return {}


def _trigger_cache_sync(
    items: List[Tuple[str, str]],
    manifest: dict,
) -> None:
    """Run cache sync in a daemon thread so it never blocks the player."""
    def _run():
        try:
            from cache_manager import get_cache_manager
            mgr = get_cache_manager()
            if mgr:
                mgr.sync_in_background(items, manifest)
        except Exception as exc:
            _LOGGER.warning("Cache sync error: %s", exc)

    t = threading.Thread(target=_run, name="cache-sync", daemon=True)
    t.start()


class PlaylistManager:
    """Maintains the ordered playback queue for this Pi's zone.

    Playlist is fetched from the server on startup and refreshed periodically.
    Photos from the photo pool are injected every photo_interval loop items.
    Announcements in the global library are interrupt-only; they enter the loop
    only when explicitly listed in the zone playlist items.

    After each successful fetch, background cache sync is triggered so that
    files are available locally on the next loop iteration.
    """

    def __init__(self) -> None:
        self._loop_items: List[PlaylistItem] = []
        self._photo_pool: List[PlaylistItem] = []
        self._queue: List[PlaylistItem] = []
        self._index: int = 0
        self._photo_interval: int = PHOTO_INTERVAL
        self._mode: str = "manual"
        self._bumper_url: str = ""

    # ── Public API ──────────────────────────────────────────────────────────────

    def fetch_playlist(self) -> bool:
        """Fetch/refresh the zone playlist from the server.  Returns True on success."""
        url = f"{SERVER_URL}/api/playlists/{urllib.parse.quote(ZONE_ID, safe='')}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            _LOGGER.warning("Could not fetch playlist from %s: %s", url, exc)
            return False

        self._photo_interval = data.get("photo_interval", PHOTO_INTERVAL)
        self._mode = data.get("mode", "manual")
        self._bumper_url = data.get("bumper_url", "")
        saved_index = self._index

        loop_items: List[PlaylistItem] = []
        photo_pool: List[PlaylistItem] = []
        # Track cacheable (subdir, filename) pairs for background sync
        cacheable: List[Tuple[str, str]] = []

        for item in data.get("items", []):
            filename = item.get("filename", "")
            mtype = item.get("media_type", "video")
            duration = item.get("photo_duration") or item.get("duration") or 30
            label = filename or item.get("url", "webpage")

            if mtype == "video":
                loop_items.append(PlaylistItem(
                    url=_file_url("videos", filename),
                    subdir="videos",
                    filename=filename,
                    display_name=filename,
                ))
                cacheable.append(("videos", filename))
            elif mtype == "announcement":
                loop_items.append(PlaylistItem(
                    url=_file_url("announcements", filename),
                    subdir="announcements",
                    filename=filename,
                    display_name=filename,
                ))
                cacheable.append(("announcements", filename))
            elif mtype == "webpage":
                page_url = _normalize_page_url(item.get("url") or "")
                if not page_url:
                    continue
                loop_items.append(PlaylistItem(
                    url=page_url,
                    is_webpage=True,
                    webpage_duration=item.get("duration", 30),
                    display_name=label,
                ))
            elif mtype == "photo":
                photo_item = PlaylistItem(
                    url=_file_url("photos", filename),
                    subdir="photos",
                    filename=filename,
                    is_photo=True,
                    photo_duration=duration,
                    display_name=filename,
                )
                cacheable.append(("photos", filename))
                if self._mode == "manual":
                    loop_items.append(photo_item)
                else:
                    photo_pool.append(photo_item)

        if not loop_items and photo_pool:
            _LOGGER.info("No videos/webpages in playlist — playing photos as loop items")
            loop_items = photo_pool
            photo_pool = []

        if not loop_items:
            _LOGGER.warning("Zone %s playlist has no playable items", ZONE_ID)
            return False

        self._loop_items = loop_items
        self._photo_pool = photo_pool
        self._rebuild_queue(shuffle=(self._mode == "auto"))
        if saved_index < len(self._queue):
            self._index = saved_index
        _LOGGER.info(
            "Playlist loaded: %d loop items, %d photos in pool, mode=%s",
            len(loop_items), len(photo_pool), self._mode,
        )

        # Kick off background cache sync (non-blocking)
        if CACHE_ENABLED and cacheable:
            manifest = _fetch_manifest()
            _trigger_cache_sync(cacheable, manifest)

        return True

    def get_current_index(self) -> int:
        return self._index

    def set_index(self, idx: int) -> None:
        self._index = idx % max(len(self._queue), 1)

    def current_item(self) -> Optional[PlaylistItem]:
        if not self._queue:
            return None
        return self._queue[self._index % len(self._queue)]

    def peek_next(self) -> Optional[PlaylistItem]:
        if not self._queue or len(self._queue) < 2:
            return None
        next_idx = (self._index + 1) % len(self._queue)
        return self._queue[next_idx]

    def peek_next_after(self, item: Optional[PlaylistItem]) -> Optional[PlaylistItem]:
        """Return the item after ``item`` in the queue (for accurate Now Playing / Up Next)."""
        if not item or not self._queue or len(self._queue) < 2:
            return self.peek_next()
        try:
            idx = self._queue.index(item)
        except ValueError:
            return self.peek_next()
        return self._queue[(idx + 1) % len(self._queue)]

    def advance(self) -> Optional[PlaylistItem]:
        """Move to the next item and return it.  Rebuilds queue when we wrap around."""
        if not self._queue:
            return None
        self._index += 1
        if self._index >= len(self._queue):
            self._index = 0
            self._rebuild_queue(shuffle=(self._mode == "auto"))
        return self._queue[self._index]

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def get_bumper_url(self) -> str:
        """Return the bumper URL configured for this zone's playlist (empty = none)."""
        return self._bumper_url

    # ── Internal ────────────────────────────────────────────────────────────────

    def _rebuild_queue(self, shuffle: bool = False) -> None:
        """Build playback queue with photos interspersed after every N loop items."""
        loop = list(self._loop_items)
        if shuffle:
            random.shuffle(loop)

        queue: List[PlaylistItem] = []
        photo_pool = list(self._photo_pool)
        random.shuffle(photo_pool)
        photo_iter = iter(photo_pool)

        for i, item in enumerate(loop):
            queue.append(item)
            if (
                self._photo_interval > 0
                and (i + 1) % self._photo_interval == 0
                and photo_pool
            ):
                try:
                    queue.append(next(photo_iter))
                except StopIteration:
                    photo_pool = list(self._photo_pool)
                    random.shuffle(photo_pool)
                    photo_iter = iter(photo_pool)
                    if photo_pool:
                        queue.append(next(photo_iter))

        self._queue = queue
        if self._index >= len(self._queue):
            self._index = 0
        _LOGGER.debug("Queue rebuilt: %d items (shuffle=%s)", len(queue), shuffle)
