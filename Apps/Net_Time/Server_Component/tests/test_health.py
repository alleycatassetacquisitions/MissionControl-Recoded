"""Tests for GET /health."""
from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "net_time"


def test_health_does_not_require_auth(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
