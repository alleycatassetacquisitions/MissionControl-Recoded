"""AlleycatTV Pi player â€” main controller.

Manages mpv via its JSON IPC socket, loops the zone playlist (with random photo
injection), handles MQTT commands, and implements interrupt/resume flow.

Entry point:  python player.py
"""
from __future__ import annotations

import json
import logging
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Optional, Tuple

from config import (
    PI_ID, ZONE_ID, MPV_SOCKET_PATH,
    STATUS_INTERVAL, PHOTO_DURATION, PLAYLIST_REFRESH_INTERVAL, CACHE_ENABLED,
    BUMPER_PATH, BUMPER_DURATION, SERVER_URL,
)
from playlist_manager import PlaylistItem, PlaylistManager
from mqtt_handler import MQTTHandler
from web_display import WebDisplay


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("alleycattv.player")

_PLAYER_VERSION = "2026.06.27-flickerfix"

_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
_DEFAULT_INTERRUPT_DURATION = 30


def _parse_interrupt_url(file_url: str) -> Tuple[str, int, bool]:
    """Parse optional #acv_duration=N and #acv_hold=1 suffixes from interrupt URLs."""
    hold = False
    duration = 0
    if "#acv_hold=1" in file_url:
        hold = True
        file_url = file_url.split("#acv_hold=")[0].rstrip("#")
    if "#acv_duration=" in file_url:
        base, _, rest = file_url.partition("#acv_duration=")
        try:
            duration = int(rest.split("&")[0].split("#")[0])
        except ValueError:
            duration = 0
        file_url = base
    return file_url, duration, hold


def _interrupt_kind(url: str) -> str:
    path = url.split("?")[0].lower()
    # Live streams → mpv (not Chromium)
    if path.startswith(("rtsp://", "rtsps://")):
        return "video"
    if any(path.endswith(ext) for ext in _PHOTO_EXT):
        return "photo"
    if any(path.endswith(ext) for ext in _VIDEO_EXT):
        return "video"
    return "webpage"


# â”€â”€ mpv IPC wrapper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MPVController:
    """Controls a running mpv process via its JSON IPC Unix socket."""

    def __init__(self, socket_path: str) -> None:
        self._path = socket_path
        self._sock: Optional[socket.socket] = None
        self._buf  = b""
        self._req_id = 0
        self._event_queue: queue.Queue[dict] = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

    def connect(self, retries: int = 20) -> bool:
        for _ in range(retries):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self._path)
                self._sock = s
                self._running = True
                self._reader_thread = threading.Thread(
                    target=self._reader, daemon=True, name="mpv-ipc-reader"
                )
                self._reader_thread.start()
                _LOGGER.info("Connected to mpv IPC socket %s", self._path)
                return True
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.25)
        _LOGGER.error("Could not connect to mpv IPC socket after %d attempts", retries)
        return False

    def send(self, command: list) -> None:
        if not self._sock:
            return
        self._req_id += 1
        msg = json.dumps({"command": command, "request_id": self._req_id}) + "\n"
        try:
            self._sock.sendall(msg.encode())
        except OSError as exc:
            _LOGGER.warning("mpv IPC send error: %s", exc)

    def load_file(self, url: str) -> None:
        self.send(["loadfile", url, "replace"])
        self.send(["set_property", "pause", False])

    def stop(self) -> None:
        self.send(["stop"])

    def pause(self, paused: bool = True) -> None:
        self.send(["set_property", "pause", paused])

    def set_volume(self, vol: int) -> None:
        self.send(["set_property", "volume", max(0, min(100, vol))])

    def wait_for_end_file(self, timeout: Optional[float] = None) -> Optional[str]:
        """Block until mpv fires an end-file event, return the reason string."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            try:
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                evt = self._event_queue.get(timeout=remaining if remaining else 1.0)
                if evt.get("event") == "end-file":
                    return evt.get("reason", "eof")
            except queue.Empty:
                if deadline is not None and time.monotonic() >= deadline:
                    return None

    def get_event_nowait(self) -> Optional[dict]:
        try:
            return self._event_queue.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        self._running = False
        try:
            self.send(["quit"])
        except Exception:
            pass
        if self._sock:
            self._sock.close()

    # â”€â”€ reader thread â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _reader(self) -> None:
        while self._running and self._sock:
            try:
                data = self._sock.recv(4096)
                if not data:
                    break
                self._buf += data
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line)
                        if "event" in msg:
                            self._event_queue.put_nowait(msg)
                    except json.JSONDecodeError:
                        pass
            except OSError:
                break


# â”€â”€ Main player â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AlleycatTVPlayer:
    def __init__(self) -> None:
        self._mpv_proc:    Optional[subprocess.Popen] = None
        self._mpv:         Optional[MPVController]    = None
        self._mqtt:        MQTTHandler                = MQTTHandler()
        self._playlist:    PlaylistManager            = PlaylistManager()
        self._web:          WebDisplay                 = WebDisplay()
        self._state:       str                        = "idle"
        self._current_url: str                        = ""
        self._current_label: str                      = ""
        self._volume:      int                        = 100
        self._webpage_lock = threading.Lock()

        # Interrupt/resume state
        self._interrupted:     bool                   = False
        self._resume_index:    int                    = 0
        self._interrupt_kind:  str                    = "video"
        self._interrupt_duration: int                 = 0
        self._interrupt_hold:    bool                   = False

        # Photo timing
        self._photo_started:   Optional[float]        = None
        self._playing_item:    Optional[PlaylistItem] = None

        # Bumper / transition between items
        self._showing_bumper:  bool                   = False
        self._bumper_started:  Optional[float]        = None
        self._webpage_active:  bool                   = False
        self._ignore_end_file: bool                   = False
        self._end_file_suppress_until: float          = 0.0

        self._start_time = time.monotonic()
        self._last_status_publish = 0.0
        self._last_playlist_refresh = 0.0

        self._shutdown = threading.Event()

    # â”€â”€ Startup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT,  self._handle_signal)

        _LOGGER.info(
            "AlleycatTV player v%s starting (PI_ID=%s ZONE=%s)",
            _PLAYER_VERSION, PI_ID, ZONE_ID,
        )

        self._mqtt.start()
        self._launch_mpv()

        # Fetch initial playlist; retry until we have content
        while not self._playlist.fetch_playlist():
            _LOGGER.warning("Playlist fetch failed â€” retrying in 10s")
            time.sleep(10)
        self._last_playlist_refresh = time.monotonic()

        self._play_current()
        self._main_loop()

    # â”€â”€ Main loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _main_loop(self) -> None:
        while not self._shutdown.is_set():
            now = time.monotonic()

            # â”€â”€ Periodic playlist refresh â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if now - self._last_playlist_refresh >= PLAYLIST_REFRESH_INTERVAL:
                if not self._webpage_active and self._playlist.fetch_playlist():
                    self._last_playlist_refresh = now

            # â”€â”€ Status publish â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            if now - self._last_status_publish >= STATUS_INTERVAL:
                self._publish_status()
                self._last_status_publish = now

            # â”€â”€ Drain MQTT command queue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            try:
                cmd = self._mqtt.cmd_queue.get_nowait()
                self._handle_command(cmd)
            except queue.Empty:
                pass

            # â”€â”€ Photo / timed interrupt duration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            playing = self._playing_item
            if self._photo_started is not None:
                limit = None
                if self._interrupted and self._interrupt_kind == "photo":
                    limit = self._interrupt_duration or _DEFAULT_INTERRUPT_DURATION
                elif playing and playing.is_photo:
                    limit = playing.photo_duration or PHOTO_DURATION
                if limit is not None and now - self._photo_started >= limit:
                    self._photo_started = None
                    if self._interrupted and self._interrupt_kind == "photo":
                        self._finish_interrupt()
                    elif playing and playing.is_photo:
                        self._advance_after_photo()

            # â”€â”€ Check for end-of-file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # Timed bumper expiry (for image bumpers or bumpers with forced max duration)
            if self._showing_bumper and self._bumper_started is not None and BUMPER_DURATION > 0:
                if now - self._bumper_started >= BUMPER_DURATION:
                    self._bumper_started = None
                    if self._mpv:
                        self._mpv.stop()
                        self._drain_mpv_events()
                        self._end_file_suppress_until = time.monotonic() + 0.5
                    self._advance_after_item()

            if self._mpv:
                evt = self._mpv.get_event_nowait()
                if evt and evt.get("event") == "end-file":
                    self._on_end_file(evt.get("reason", "eof"))

            time.sleep(0.05)

        self._cleanup()

    # â”€â”€ Command handlers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _handle_command(self, cmd) -> None:
        # Fabric delivers {"action": str, "payload": dict}
        if isinstance(cmd, dict):
            action = cmd.get("action")
            payload = cmd.get("payload") or {}
            if action == "interrupt":
                self._interrupt(payload.get("file_url") or "")
            elif action == "play":
                if self._interrupted:
                    self._finish_interrupt()
                else:
                    self._resume_normal()
            elif action == "stop":
                if self._interrupted:
                    self._finish_interrupt()
                else:
                    self._state = "stopped"
                    self._current_label = ""
                    self._playing_item = None
                    self._web.close()
                    if self._mpv:
                        self._mpv.stop()
            elif action == "reload":
                _LOGGER.info("Reloading playlist from server")
                if self._playlist.fetch_playlist():
                    if (
                        not self._interrupted
                        and not self._webpage_active
                        and self._state == "stopped"
                    ):
                        self._state = "idle"
                        self._play_current()
                else:
                    _LOGGER.warning("Playlist reload failed — keeping current playback")
            elif action == "volume":
                self._volume = max(0, min(100, int(payload.get("volume", 80))))
                if self._mpv:
                    self._mpv.set_volume(self._volume)
                self._publish_status()
            else:
                _LOGGER.debug("Unknown command action: %s", action)
            return
        _LOGGER.warning("Ignoring non-dict command: %r", cmd)

    # â”€â”€ Interrupt / resume â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _interrupt(self, file_url: str) -> None:
        if not file_url:
            _LOGGER.warning("InterruptCmd received with empty file_url, ignoring")
            return
        file_url, duration_hint, hold = _parse_interrupt_url(file_url)
        kind = _interrupt_kind(file_url)
        _LOGGER.info(
            "INTERRUPT: saving index=%d, kind=%s, hold=%s, playing %s",
            self._playlist.get_current_index(), kind, hold, file_url,
        )
        self._resume_index = self._playlist.get_current_index()
        self._interrupted = True
        self._interrupt_kind = kind
        self._interrupt_hold = hold
        self._interrupt_duration = duration_hint
        self._state = "interrupted"
        self._current_url = file_url
        self._current_label = os.path.basename(file_url.split("?")[0]) or file_url
        self._photo_started = None
        self._web.close()

        if kind == "webpage":
            if hold:
                threading.Thread(
                    target=self._interrupt_webpage_hold,
                    args=(file_url,),
                    daemon=True,
                    name="interrupt-webpage-hold",
                ).start()
            else:
                show_duration = duration_hint or _DEFAULT_INTERRUPT_DURATION
                threading.Thread(
                    target=self._interrupt_webpage,
                    args=(file_url, show_duration),
                    daemon=True,
                    name="interrupt-webpage",
                ).start()
            self._publish_status()
            return

        if kind == "photo":
            self._interrupt_duration = duration_hint or _DEFAULT_INTERRUPT_DURATION
            if not hold:
                self._photo_started = time.monotonic()
        self._playing_item = None
        self._mpv_load(file_url)
        self._publish_status()

    def _interrupt_webpage(self, url: str, duration: int) -> None:
        with self._webpage_lock:
            if not self._interrupted:
                return
            self._web.show(url, duration)
        if self._interrupted and not self._interrupt_hold:
            self._finish_interrupt()

    def _interrupt_webpage_hold(self, url: str) -> None:
        with self._webpage_lock:
            if not self._interrupted:
                return
            if not self._web.open(url):
                self._finish_interrupt()
                return
            while self._interrupted and self._interrupt_hold:
                time.sleep(0.25)
            self._web.close()
        if self._interrupted:
            self._finish_interrupt()

    def _finish_interrupt(self) -> None:
        """End an announcement and resume the saved playlist position."""
        self._resume_after_interrupt()

    def _resume_after_interrupt(self) -> None:
        if not self._interrupted:
            return
        _LOGGER.info("Resuming playlist at index %d", self._resume_index)
        self._interrupted = False
        self._interrupt_kind = "video"
        self._interrupt_duration = 0
        self._interrupt_hold = False
        self._web.close()
        self._drain_mpv_events()
        self._playlist.set_index(self._resume_index)
        self._state = "playing"
        self._photo_started = None
        self._play_current()
        self._publish_status()

    def _resume_normal(self) -> None:
        if self._state == "stopped":
            self._state = "idle"
            self._play_current()
        elif self._state == "paused" and self._mpv:
            self._mpv.pause(False)
            self._state = "playing"

    # â”€â”€ Playback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _play_current(self) -> None:
        item = self._playlist.current_item()
        if item is None:
            _LOGGER.warning("No item to play")
            return
        self._play_item(item)

    def _play_item(self, item: PlaylistItem) -> None:
        if self._state == "stopped":
            return
        _LOGGER.info("Playing: %s", item.url)
        self._playing_item = item
        self._current_url = item.url
        self._current_label = item.basename
        self._state = "playing"
        self._photo_started = time.monotonic() if item.is_photo else None

        if item.is_webpage:
            self._web.close()
            if self._mpv:
                self._mpv.stop()
            threading.Thread(
                target=self._play_webpage,
                args=(item,),
                daemon=True,
                name="webpage-display",
            ).start()
            self._publish_status()
            return

        # Close browser overlay and ensure mpv is running before video/photo playback.
        self._web.close()
        self._webpage_active = False

        if self._mpv:
            self._mpv_load(item.url)
        self._publish_status()

    @staticmethod
    def _is_natural_eof(reason) -> bool:
        """True only when mpv finished playing a file (not loadfile replace/stop)."""
        if reason in (0, "eof"):
            return True
        if isinstance(reason, int):
            return reason == 0
        if isinstance(reason, str):
            if reason == "eof":
                return True
            try:
                return int(reason) == 0
            except ValueError:
                pass
        return False

    def _drain_mpv_events(self) -> None:
        """Discard stale end-file events left over from loadfile replace."""
        if not self._mpv:
            return
        while self._mpv.get_event_nowait() is not None:
            pass

    def _mpv_load(self, url: str) -> None:
        """Load a file in mpv and ignore spurious end-file events from the replace."""
        if not self._mpv:
            return
        self._ignore_end_file = True
        self._mpv.load_file(url)
        self._drain_mpv_events()
        self._end_file_suppress_until = time.monotonic() + 0.75
        self._ignore_end_file = False

    def _advance_after_photo(self) -> None:
        """Advance after a timed photo slide (do not rely on mpv end-file with keep-open)."""
        self._ignore_end_file = True
        if self._mpv:
            self._mpv.stop()
            self._drain_mpv_events()
            self._end_file_suppress_until = time.monotonic() + 0.75
        self._advance_after_item()
        self._ignore_end_file = False
        self._publish_status()

    def _play_webpage(self, item: PlaylistItem) -> None:
        try:
            with self._webpage_lock:
                if self._state == "stopped":
                    return
                self._webpage_active = True
                self._web.show(item.url, item.webpage_duration)
        finally:
            self._webpage_active = False
            self._web.close()
        if self._state == "stopped":
            return
        if self._mpv:
            self._mpv.pause(False)
        self._advance_after_item()

    def _advance_after_item(self) -> None:
        if self._state == "stopped":
            return
        if self._showing_bumper:
            # Bumper just finished — now play the next real item
            self._showing_bumper = False
            self._bumper_started = None
            next_item = self._playlist.advance()
            if next_item:
                self._play_item(next_item)
            return
        bumper = self._playlist.get_bumper_url() or BUMPER_PATH
        if bumper and (os.path.exists(bumper) or bumper.startswith(("http://", "https://", "file://"))):
            # Show bumper before advancing; playlist index advances when bumper ends
            _LOGGER.debug("Showing transition bumper: %s", bumper)
            self._showing_bumper = True
            self._playing_item = None
            self._current_label = "transition"
            if BUMPER_DURATION > 0:
                self._bumper_started = time.monotonic()
            self._mpv_load(bumper)
            return
        next_item = self._playlist.advance()
        if next_item:
            self._play_item(next_item)

    def _on_end_file(self, reason: str) -> None:
        if time.monotonic() < self._end_file_suppress_until:
            return
        if self._state == "stopped" or self._ignore_end_file or self._webpage_active:
            return
        if not self._is_natural_eof(reason):
            _LOGGER.debug("Ignoring mpv end-file reason=%r (not natural eof)", reason)
            return
        # mpv may send reason as int (0=eof) or string
        if self._interrupted:
            if self._interrupt_hold:
                return
            if self._interrupt_kind == "video":
                _LOGGER.info("Announcement video ended â€” resuming playlist")
                self._finish_interrupt()
            return
        if self._showing_bumper:
            _LOGGER.debug("Bumper ended — advancing to next item")
            self._advance_after_item()
            return
        if self._playing_item and self._playing_item.is_photo:
            return
        if self._state in ("playing", "idle"):
            _LOGGER.info("End of file (%s) â€” advancing playlist", reason)
            self._advance_after_item()

    # â”€â”€ mpv process management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _launch_mpv(self) -> None:
        if os.path.exists(MPV_SOCKET_PATH):
            os.unlink(MPV_SOCKET_PATH)

        base_cmd = [
            "mpv",
            "--fullscreen",
            "--no-osd-bar",
            "--no-osc",
            "--no-input-default-bindings",
            "--no-terminal",
            "--idle=yes",
            f"--input-ipc-server={MPV_SOCKET_PATH}",
            f"--volume={self._volume}",
            "--loop-file=no",
            "--image-display-duration=inf",
        ]
        # Cache only â€” keep-open=always prevents end-file from advancing the playlist.
        enhanced_flags = [
            "--force-window=yes",
            "--cache=yes",
            "--demuxer-max-bytes=50M",
            "--demuxer-lavf-o=rtsp_transport=tcp",
            "--mute=no",
            "--ao=alsa",
            "--audio-device=alsa/hdmi:CARD=vc4hdmi0,DEV=0",
        ]
        if os.environ.get("WAYLAND_DISPLAY"):
            enhanced_flags.extend([
                "--vo=gpu",
                "--gpu-context=wayland",
            ])

        for extra in (enhanced_flags, []):
            if os.path.exists(MPV_SOCKET_PATH):
                os.unlink(MPV_SOCKET_PATH)
            cmd = base_cmd[:6] + extra + base_cmd[6:]
            label = "enhanced" if extra else "minimal"
            _LOGGER.info("Launching mpv (%s)...", label)
            err_log = subprocess.PIPE
            self._mpv_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=err_log,
            )
            self._mpv = MPVController(MPV_SOCKET_PATH)
            if self._mpv.connect(retries=40):
                return
            stderr = ""
            if self._mpv_proc.stderr:
                try:
                    stderr = self._mpv_proc.stderr.read().decode(errors="replace").strip()
                except Exception:
                    pass
            rc = self._mpv_proc.poll()
            _LOGGER.warning(
                "mpv (%s) IPC connect failed (exit=%s)%s",
                label,
                rc,
                f": {stderr[-500:]}" if stderr else "",
            )
            try:
                self._mpv_proc.terminate()
                self._mpv_proc.wait(timeout=3)
            except Exception:
                try:
                    self._mpv_proc.kill()
                except Exception:
                    pass
            self._mpv.close()
            self._mpv = None

        _LOGGER.error(
            "Could not connect to mpv â€” is mpv installed, and is alleycattv-kiosk running?"
        )
        sys.exit(1)

    # â”€â”€ Status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _publish_status(self) -> None:
        if self._state == "stopped":
            current_file = ""
            next_file = ""
        else:
            playing = self._playing_item
            current_file = playing.basename if playing else (
                self._current_label or (
                    os.path.basename(self._current_url) if self._current_url else ""
                )
            )
            nxt = self._playlist.peek_next_after(playing) if playing else self._playlist.peek_next()
            next_file = nxt.basename if nxt else ""
        status = {
            "state": self._state,
            "current_file": current_file,
            "next_file": next_file,
            "playlist_index": self._playlist.get_current_index(),
            "ip": self._get_local_ip(),
            "uptime": int(time.monotonic() - self._start_time),
        }
        self._mqtt.publish_status_json(status)

        if CACHE_ENABLED:
            try:
                from cache_manager import get_cache_manager
                import urllib.request

                mgr = get_cache_manager()
                if mgr:
                    report = mgr.get_status()
                    url = f"{SERVER_URL}/api/devices/{PI_ID}/cache"
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(
                            {
                                "files": report.get("files", []),
                                "cache_bytes": report.get("disk_used", 0),
                                "free_bytes": report.get("disk_free"),
                            }
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=5)
            except Exception as exc:
                _LOGGER.debug("Cache HTTP report failed: %s", exc)

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "0.0.0.0"
        finally:
            s.close()

    # â”€â”€ Shutdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _handle_signal(self, signum, frame) -> None:
        _LOGGER.info("Signal %d received â€” shutting down", signum)
        self._shutdown.set()

    def _cleanup(self) -> None:
        _LOGGER.info("Shutting down AlleycatTV player")
        self._mqtt.publish_offline()
        self._mqtt.stop()
        self._web.close()
        if self._mpv:
            self._mpv.close()
        if self._mpv_proc:
            self._mpv_proc.terminate()


# â”€â”€ Entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

if __name__ == "__main__":
    AlleycatTVPlayer().run()
