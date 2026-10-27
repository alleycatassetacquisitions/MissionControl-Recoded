#!/usr/bin/env python3
"""Mission Control venue update agent — runs on the Proxmox HOST.

Wraps update-mission-control.sh for Core Configurator (HA → this agent).

Bind: 0.0.0.0:8722 (VENUE_UPDATER_PORT)
Auth: Bearer VENUE_UPDATER_TOKEN

  GET  /health
  GET  /status
  POST /check
  POST /apply
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ.get("VENUE_UPDATER_TOKEN", "").strip()
PORT = int(os.environ.get("VENUE_UPDATER_PORT", "8722"))
STATE_FILE = Path(
    os.environ.get("MC_STATE_FILE", "/root/mission-control-install-state.json")
)
UPDATE_SCRIPT = Path(
    os.environ.get(
        "MC_UPDATE_SCRIPT",
        "/root/mission-control-src/ProxmoxInstallFiles/update-mission-control.sh",
    )
)
SRC_ROOT = Path(os.environ.get("MC_SRC_ROOT", "/root/mission-control-src"))

_lock = threading.Lock()
_last_check: dict | None = None
_apply_running = False
_last_apply: dict | None = None


def _load_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _run_update(*args: str, timeout: int = 600) -> tuple[int, str, str]:
    if not UPDATE_SCRIPT.is_file():
        return 127, "", f"missing updater: {UPDATE_SCRIPT}"
    env = os.environ.copy()
    env["MC_SRC_ROOT"] = str(SRC_ROOT)
    env["MC_STATE_FILE"] = str(STATE_FILE)
    proc = subprocess.run(
        ["bash", str(UPDATE_SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _parse_check_json(stdout: str) -> dict:
    """Updater --check --json prints one JSON object on stdout."""
    text = (stdout or "").strip()
    if not text:
        return {"status": "error", "detail": "empty check output"}
    # Find last JSON object in case of banners
    start = text.rfind("{")
    if start < 0:
        return {"status": "error", "detail": text[-500:]}
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return {"status": "error", "detail": text[-500:]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _auth_ok(self) -> bool:
        if not TOKEN:
            return False
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Bearer "):
            return False
        return hdr[7:].strip() == TOKEN

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _require_auth(self) -> bool:
        if self._auth_ok():
            return True
        self._send(401, {"detail": "unauthorized"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, {"status": "ok", "service": "mc_venue_update"})
            return
        if path == "/status":
            if not self._require_auth():
                return
            state = _load_state()
            self._send(
                200,
                {
                    "status": "ok",
                    "installed_release": state.get("release"),
                    "last_updated_at": state.get("last_updated_at"),
                    "commit": state.get("commit"),
                    "apply_running": _apply_running,
                    "last_check": _last_check,
                    "last_apply": _last_apply,
                },
            )
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _last_check, _apply_running, _last_apply
        path = self.path.split("?", 1)[0]
        if path not in ("/check", "/apply"):
            self._send(404, {"detail": "not found"})
            return
        if not self._require_auth():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            _ = self.rfile.read(length)

        if path == "/check":
            with _lock:
                code, out, err = _run_update("--check", "--json", timeout=120)
            result = _parse_check_json(out)
            if code not in (0, 1) and result.get("status") == "error":
                result = {
                    "status": "error",
                    "detail": (err or out or f"exit {code}")[-800:],
                }
            elif "status" not in result:
                result["status"] = (
                    "update_available" if code == 1 else "up_to_date"
                )
            _last_check = result
            self._send(200 if result.get("status") != "error" else 500, result)
            return

        # /apply
        if _apply_running:
            self._send(409, {"status": "busy", "detail": "apply already running"})
            return

        def _job() -> None:
            global _apply_running, _last_apply
            _apply_running = True
            try:
                code, out, err = _run_update("--yes", "--json", timeout=1800)
                body = _parse_check_json(out)
                if "status" not in body:
                    body = {
                        "status": "ok" if code == 0 else "error",
                        "exit_code": code,
                        "stdout_tail": (out or "")[-1000:],
                        "stderr_tail": (err or "")[-1000:],
                    }
                _last_apply = body
            except Exception as exc:  # noqa: BLE001
                _last_apply = {"status": "error", "detail": str(exc)}
            finally:
                _apply_running = False

        threading.Thread(target=_job, daemon=True).start()
        self._send(202, {"status": "started", "detail": "apply running"})


def main() -> None:
    if not TOKEN:
        sys.stderr.write("VENUE_UPDATER_TOKEN is required\n")
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("mc-venue-update listening on 0.0.0.0:%s\n" % PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
