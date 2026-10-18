#!/usr/bin/env python3
"""Net Time host clock agent — runs on the Proxmox HOST (not in the LXC).

LXC guests share the host clock and usually cannot call settimeofday.
Offline Sync in the Net Time CT POSTs here; this process sets the host clock
so chrony in the CT serves the new time to FDN/PDN clients.

Bind: 0.0.0.0:8721 (override with NET_TIME_HOST_CLOCK_PORT)
Auth: Bearer NET_TIME_API_TOKEN (same token as the Net Time LXC API)

  POST /sync  {"iso8601":"2026-10-18T21:00:00Z"}
  GET  /health
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TOKEN = os.environ.get("NET_TIME_API_TOKEN", "").strip()
PORT = int(os.environ.get("NET_TIME_HOST_CLOCK_PORT", "8721"))


def _parse_iso(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _set_clock(when: datetime) -> None:
    stamp = when.strftime("%Y-%m-%d %H:%M:%S")
    proc = subprocess.run(
        ["date", "-u", "-s", stamp],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "date failed").strip())


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

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            self._send(404, {"detail": "not found"})
            return
        self._send(200, {"status": "ok", "service": "net_time_host_clock"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/sync":
            self._send(404, {"detail": "not found"})
            return
        if not self._auth_ok():
            self._send(401, {"detail": "Invalid or missing Bearer token."})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(422, {"detail": "Invalid JSON"})
            return
        iso = str(payload.get("iso8601") or "").strip()
        if not iso:
            self._send(422, {"detail": "iso8601 is required"})
            return
        try:
            when = _parse_iso(iso)
            _set_clock(when)
        except Exception as err:  # noqa: BLE001
            self._send(502, {"detail": f"Failed to set host clock: {err}"})
            return
        applied = when.isoformat().replace("+00:00", "Z")
        self._send(200, {"applied_iso": applied, "via": "host"})


def main() -> None:
    if not TOKEN:
        print("NET_TIME_API_TOKEN is required", file=sys.stderr)
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"net-time host clock agent on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
