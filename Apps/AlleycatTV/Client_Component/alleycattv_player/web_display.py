"""WebDisplay — launches Chromium in kiosk mode for webpage announcement items.

The kiosk extension at /opt/alleycattv/kiosk_ext/ is loaded automatically if
present. It injects CSS to hide the mouse cursor and scrollbars on every page,
which is the right fix for the "scoreboard has a cursor and scrollbar" problem.

To install the extension (done by install.sh / deploy steps):
  mkdir -p /opt/alleycattv/kiosk_ext
  copy: kiosk_ext/manifest.json + kiosk_ext/content.js  → /opt/alleycattv/kiosk_ext/
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Optional

_LOGGER = logging.getLogger(__name__)

_CHROMIUM_BINS = [
    "chromium-browser",
    "chromium",
    "google-chrome-stable",
    "google-chrome",
]
_KIOSK_EXT_DIR = "/opt/alleycattv/kiosk_ext"


def _find_chromium() -> str:
    import shutil
    for name in _CHROMIUM_BINS:
        if shutil.which(name):
            return name
    return _CHROMIUM_BINS[0]


def _build_cmd(url: str) -> list[str]:
    chromium = _find_chromium()
    cmd = [
        chromium,
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--no-default-browser-check",
        "--no-first-run",
        "--disable-session-crashed-bubble",
        "--disable-features=TranslateUI,Translate",
        "--disable-pinch",
        "--overscroll-history-navigation=0",
        "--disable-background-networking",
        "--disable-sync",
        "--metrics-recording-only",
        "--check-for-update-interval=31536000",
    ]

    if os.environ.get("WAYLAND_DISPLAY"):
        cmd += ["--ozone-platform=wayland", "--enable-features=UseOzonePlatform"]

    if os.path.isdir(_KIOSK_EXT_DIR):
        cmd += [
            f"--load-extension={_KIOSK_EXT_DIR}",
            f"--disable-extensions-except={_KIOSK_EXT_DIR}",
        ]
    else:
        _LOGGER.warning(
            "Kiosk extension not found at %s — cursor/scrollbars will be visible. "
            "Run install.sh to fix this.",
            _KIOSK_EXT_DIR,
        )

    cmd.append(url)
    return cmd


class WebDisplay:
    """Controls a fullscreen Chromium window for URL-based playlist items.

    Public API matches what AlleycatTVPlayer expects:
      show(url, duration) — display for N seconds then close (blocking)
      open(url) → bool   — open and keep running; returns False if Chromium crashed
      close()            — kill the Chromium process (also aborts an in-flight show)
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._cancelled = False
        self._chromium_died = False

    @property
    def cancelled(self) -> bool:
        """True if the last ``show()`` was aborted by ``close()`` (e.g. reload)."""
        return self._cancelled

    @property
    def chromium_died(self) -> bool:
        """True if Chromium exited before the scheduled duration ended."""
        return self._chromium_died

    def show(self, url: str, duration: int) -> None:
        """Open URL, display for `duration` seconds (blocking), then close.

        Returns early if Chromium exits or ``close()`` is called (playlist reload).
        """
        self.close()
        self._cancel.clear()
        self._cancelled = False
        self._chromium_died = False
        self._launch(url)
        deadline = time.monotonic() + max(1, int(duration))
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                self._cancelled = True
                _LOGGER.info("Webpage display cancelled early for %s", url)
                break
            with self._lock:
                proc = self._proc
                dead = proc is None or proc.poll() is not None
            if dead:
                self._chromium_died = True
                _LOGGER.warning(
                    "Chromium exited early during webpage display (%s) — "
                    "not sleeping the remaining duration",
                    url,
                )
                break
            time.sleep(0.5)
        self.close()

    def open(self, url: str) -> bool:
        """Open URL and keep running (for hold-mode interrupts).

        Returns True if Chromium started successfully, False otherwise.
        """
        self.close()
        self._cancel.clear()
        self._cancelled = False
        self._chromium_died = False
        self._launch(url)
        time.sleep(2)
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        """Kill the running Chromium process and abort an in-flight ``show()``."""
        self._cancel.set()
        with self._lock:
            if self._proc is None:
                return
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=2)
            except Exception as exc:
                _LOGGER.debug("Chromium close error: %s", exc)
            self._proc = None

    def _launch(self, url: str) -> None:
        cmd = _build_cmd(url)
        env = {**os.environ}
        try:
            with self._lock:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                )
            _LOGGER.info("Launched Chromium pid=%d for %s", self._proc.pid, url)
        except FileNotFoundError:
            _LOGGER.error(
                "Chromium not found (%s). Install with: sudo apt install chromium-browser",
                cmd[0],
            )
        except Exception as exc:
            _LOGGER.error("Could not launch Chromium: %s", exc)
