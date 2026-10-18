"""Tests for POST /timezone."""
from fastapi.testclient import TestClient


def test_timezone_requires_auth(client: TestClient):
    resp = client.post("/timezone", json={"timezone": "America/Chicago"})
    assert resp.status_code == 401


def test_timezone_sets_iana(client: TestClient, auth_headers: dict[str, str], reset_ops):
    resp = client.post(
        "/timezone",
        headers=auth_headers,
        json={"timezone": "America/Chicago"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/Chicago"
    assert reset_ops.timezone == "America/Chicago"


def test_timezone_rejects_unknown(client: TestClient, auth_headers: dict[str, str]):
    resp = client.post(
        "/timezone",
        headers=auth_headers,
        json={"timezone": "Not/A_Zone"},
    )
    assert resp.status_code == 422
