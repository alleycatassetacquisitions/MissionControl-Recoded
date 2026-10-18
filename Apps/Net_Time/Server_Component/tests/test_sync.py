"""Tests for POST /sync."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from chrony_ops import FakeChronyOps
from main import set_ops


def test_sync_requires_auth(client: TestClient):
    resp = client.post("/sync", json={"iso8601": "2026-10-18T20:00:00Z"})
    assert resp.status_code == 401


def test_sync_applies_iso(client: TestClient, auth_headers: dict[str, str], reset_ops):
    when = "2026-10-18T20:15:30.000Z"
    resp = client.post("/sync", headers=auth_headers, json={"iso8601": when})
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied_iso"] == "2026-10-18T20:15:30Z"
    assert body["via"] == "local"
    assert body["status"]["public_ntp"] == "unavailable"
    assert reset_ops.last_applied == datetime(2026, 10, 18, 20, 15, 30, tzinfo=timezone.utc)
    # Clock advanced to requested time
    assert abs(body["status"]["unix"] - reset_ops.last_applied.timestamp()) < 0.01


def test_sync_rejects_bad_iso(client: TestClient, auth_headers: dict[str, str]):
    resp = client.post("/sync", headers=auth_headers, json={"iso8601": "not-a-date"})
    assert resp.status_code == 422


def test_sync_apply_failure(client: TestClient, auth_headers: dict[str, str]):
    set_ops(FakeChronyOps(fail_apply=True))
    resp = client.post(
        "/sync",
        headers=auth_headers,
        json={"iso8601": "2026-10-18T20:00:00Z"},
    )
    assert resp.status_code == 502
