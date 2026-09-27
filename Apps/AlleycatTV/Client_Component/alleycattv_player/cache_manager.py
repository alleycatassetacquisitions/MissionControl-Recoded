"""AlleycatTV local video cache manager.

Downloads playlist files to local storage so each Pi plays from disk rather than
streaming over the network on every loop.  Fully non-blocking: background downloads
never stall playback.  The foreground player falls back to the HTTP URL while a
file is being fetched; on the next playlist refresh the local path is used.

Usage
-----
Call ``get_cache_manager()`` to obtain the process-wide singleton.
``playlist_manager`` calls ``sync_in_background()`` after each playlist fetch.
``mqtt_handler`` calls ``delete_file()``, ``purge()``, and ``sync_now()`` in
response to remote management commands from the HA Content Manager panel.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import CACHE_DIR, CACHE_MAX_GB, CACHE_ENABLED, SERVER_URL

_LOGGER = logging.getLogger(__name__)
_META_FILE = os.path.join(CACHE_DIR, ".meta.json")
_CACHE_MAX_BYTES = int(CACHE_MAX_GB * 1024 ** 3)
_SUBDIRS = ("videos", "photos", "announcements")


class CacheManager:
    """Manages the local file cache for this Pi.

    Thread safety: all public methods acquire ``_lock`` before touching the meta
    dict or the file system. The background download worker also holds the lock
    only when updating meta — actual HTTP download happens outside the lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._download_queue: List[Tuple[str, str, str]] = []  # (subdir, filename, url)
        self._downloading: set = set()  # keys currently being fetched
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pending_sync: Optional[threading.Event] = None  # signalled after sync completes
        self._manifest: Dict[str, List[Dict[str, Any]]] = {}

        if CACHE_ENABLED:
            self._ensure_dirs()
            self._load_meta()
            self._start_worker()

    # ── Directory / meta helpers ────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        for sub in _SUBDIRS:
            Path(CACHE_DIR, sub).mkdir(parents=True, exist_ok=True)

    def _load_meta(self) -> None:
        try:
            if os.path.exists(_META_FILE):
                with open(_META_FILE) as f:
                    self._meta = json.load(f)
        except Exception as exc:
            _LOGGER.warning("Could not load cache meta: %s — starting fresh", exc)
            self._meta = {}

    def _save_meta(self) -> None:
        try:
            with open(_META_FILE, "w") as f:
                json.dump(self._meta, f, indent=2)
        except Exception as exc:
            _LOGGER.warning("Could not save cache meta: %s", exc)

    def _key(self, subdir: str, filename: str) -> str:
        return f"{subdir}/{filename}"

    def _local_path(self, subdir: str, filename: str) -> str:
        return os.path.join(CACHE_DIR, subdir, filename)

    # ── Background download worker ──────────────────────────────────────────────

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="alleycattv-cache-worker",
            daemon=True,
        )
        self._worker_thread.start()

    def _worker_loop(self) -> None:
        _LOGGER.info("Cache worker started (max %.1f GB at %s)", CACHE_MAX_GB, CACHE_DIR)
        while not self._stop_event.is_set():
            item = None
            with self._lock:
                for entry in list(self._download_queue):
                    subdir, filename, url = entry
                    key = self._key(subdir, filename)
                    if key not in self._downloading:
                        item = entry
                        self._download_queue.remove(entry)
                        self._downloading.add(key)
                        break
            if item is None:
                time.sleep(2)
                continue
            subdir, filename, url = item
            self._download_file(subdir, filename, url)

    def _download_file(self, subdir: str, filename: str, url: str) -> None:
        key = self._key(subdir, filename)
        dest = self._local_path(subdir, filename)
        tmp = dest + ".tmp"
        try:
            _LOGGER.info("Downloading %s -> %s", url, dest)
            with urllib.request.urlopen(url, timeout=60) as resp:
                with open(tmp, "wb") as out:
                    shutil.copyfileobj(resp, out)
            os.replace(tmp, dest)
            stat = os.stat(dest)
            with self._lock:
                self._meta[key] = {
                    "subdir": subdir,
                    "filename": filename,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "cached_at": time.time(),
                }
                self._save_meta()
                self._downloading.discard(key)
            _LOGGER.info("Cached %s (%.1f MB)", filename, stat.st_size / 1024 / 1024)
        except Exception as exc:
            _LOGGER.warning("Cache download failed for %s: %s", url, exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            with self._lock:
                self._downloading.discard(key)

    # ── Public API ──────────────────────────────────────────────────────────────

    def sync_in_background(
        self,
        playlist_items: List[Tuple[str, str]],   # [(subdir, filename), ...]
        manifest: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        """Queue missing or stale playlist files for background download.

        ``manifest`` is the server's manifest dict:
        ``{subdir: [{filename, size_bytes, mtime}]}``
        """
        if not CACHE_ENABLED:
            return

        self._manifest = manifest
        manifest_lookup: Dict[str, Dict[str, Any]] = {}
        for subdir, entries in manifest.items():
            for entry in entries:
                k = self._key(subdir, entry["filename"])
                manifest_lookup[k] = entry

        with self._lock:
            current_keys = {self._key(s, f) for s, f in playlist_items}
            for subdir, filename in playlist_items:
                key = self._key(subdir, filename)
                local = self._local_path(subdir, filename)
                meta = self._meta.get(key)
                server_info = manifest_lookup.get(key)

                # Determine if we need to (re)download
                needs_download = False
                if not os.path.exists(local):
                    needs_download = True
                elif meta and server_info:
                    if meta.get("size_bytes") != server_info.get("size_bytes"):
                        needs_download = True
                        _LOGGER.info("Stale cache for %s (size mismatch) — will re-download", filename)
                elif not meta:
                    needs_download = True

                if needs_download:
                    http_url = f"{SERVER_URL}/media/{subdir}/{urllib.request.quote(filename)}"
                    already_queued = any(
                        s == subdir and fn == filename
                        for s, fn, _ in self._download_queue
                    )
                    if not already_queued and key not in self._downloading:
                        self._download_queue.append((subdir, filename, http_url))

            self._evict_lru(current_keys)

    def evict_lru(self, needed_bytes: int = 0) -> None:
        """Public wrapper — evict oldest cached files until needed_bytes is free."""
        with self._lock:
            self._evict_lru(set(self._meta.keys()), needed_bytes)

    def _evict_lru(self, keep_keys: set, needed_bytes: int = 0) -> None:
        """Evict files not in keep_keys first; then by oldest cached_at.
        Must be called with _lock held."""
        disk_usage = sum(
            m.get("size_bytes", 0) for m in self._meta.values()
        )
        limit = _CACHE_MAX_BYTES - needed_bytes
        if disk_usage <= limit:
            return

        evict_candidates = sorted(
            self._meta.items(),
            key=lambda kv: (
                kv[0] in keep_keys,          # files not in playlist first
                kv[1].get("cached_at", 0),   # oldest first within each group
            )
        )
        for key, meta in evict_candidates:
            if disk_usage <= limit:
                break
            subdir = meta.get("subdir", "")
            filename = meta.get("filename", "")
            local = self._local_path(subdir, filename)
            try:
                if os.path.exists(local):
                    os.unlink(local)
                    disk_usage -= meta.get("size_bytes", 0)
                    _LOGGER.info("Evicted %s/%s (LRU)", subdir, filename)
            except OSError as exc:
                _LOGGER.warning("Could not evict %s: %s", local, exc)
            self._meta.pop(key, None)
        self._save_meta()

    def get_local_path(self, subdir: str, filename: str) -> Optional[str]:
        """Return the local file path if the file is fully cached, else None."""
        if not CACHE_ENABLED:
            return None
        key = self._key(subdir, filename)
        local = self._local_path(subdir, filename)
        with self._lock:
            if key in self._meta and os.path.exists(local):
                return local
        return None

    def get_status(self) -> Dict[str, Any]:
        """Return disk usage and file inventory for MQTT status publishing."""
        try:
            stat = shutil.disk_usage(CACHE_DIR)
            disk_total = stat.total
            disk_used = stat.used
            disk_free = stat.free
        except OSError:
            disk_total = disk_used = disk_free = 0

        with self._lock:
            files = [
                {
                    "subdir": m.get("subdir", ""),
                    "filename": m.get("filename", ""),
                    "size_bytes": m.get("size_bytes", 0),
                    "cached_at": m.get("cached_at", 0),
                }
                for m in self._meta.values()
            ]

        return {
            "disk_total": disk_total,
            "disk_used": disk_used,
            "disk_free": disk_free,
            "cache_max_bytes": _CACHE_MAX_BYTES,
            "cache_dir": CACHE_DIR,
            "files": files,
            "pending_downloads": len(self._download_queue),
        }

    def delete_file(self, subdir: str, filename: str) -> None:
        """Remove a specific file from the local cache."""
        key = self._key(subdir, filename)
        local = self._local_path(subdir, filename)
        with self._lock:
            try:
                if os.path.exists(local):
                    os.unlink(local)
                    _LOGGER.info("Deleted cached file %s/%s", subdir, filename)
            except OSError as exc:
                _LOGGER.warning("Could not delete %s: %s", local, exc)
            self._meta.pop(key, None)
            self._save_meta()

    def purge(self) -> None:
        """Wipe the entire local cache."""
        with self._lock:
            for sub in _SUBDIRS:
                folder = Path(CACHE_DIR, sub)
                if folder.exists():
                    shutil.rmtree(str(folder), ignore_errors=True)
                    folder.mkdir(parents=True, exist_ok=True)
            try:
                if os.path.exists(_META_FILE):
                    os.unlink(_META_FILE)
            except OSError:
                pass
            self._meta.clear()
            self._download_queue.clear()
            self._downloading.clear()
        _LOGGER.info("Cache purged")

    def sync_now(self) -> None:
        """Trigger an immediate re-sync using the last known playlist + manifest.

        The playlist_manager will perform the actual sync next time fetch_playlist()
        is called. This method signals the background worker to wake up sooner.
        """
        _LOGGER.info("Cache sync requested via MQTT — will apply on next playlist refresh")


# ── Module-level singleton ──────────────────────────────────────────────────────

_instance: Optional[CacheManager] = None
_instance_lock = threading.Lock()


def get_cache_manager() -> Optional[CacheManager]:
    """Return the process-wide CacheManager, creating it on first call."""
    global _instance
    if not CACHE_ENABLED:
        return None
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CacheManager()
    return _instance
