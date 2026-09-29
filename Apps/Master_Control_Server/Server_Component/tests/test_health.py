"""Tests for GET /health.

/health is unauthenticated — polled by the Registration DataUpdateCoordinator
to detect MCS availability. It reflects the currently configured Central URLs.
"""
from fastapi.testclient import TestClient

from main import _config


def test_health_returns_ok(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_does_not_require_auth(client: TestClient):
    """No Authorization header — must still succeed."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_reflects_central_primary(client: TestClient):
    _config["central_primary"] = "http://cloud.example.com"
    resp = client.get("/health")
    assert resp.json()["central_primary"] == "http://cloud.example.com"


def test_health_reflects_central_secondary(client: TestClient):
    _config["central_secondary"] = "http://lan.example.com"
    resp = client.get("/health")
    assert resp.json()["central_secondary"] == "http://lan.example.com"


def test_health_empty_urls_when_not_configured(client: TestClient):
    _config["central_primary"] = ""
    _config["central_secondary"] = ""
    resp = client.get("/health")
    data = resp.json()
    assert data["central_primary"] == ""
    assert data["central_secondary"] == ""
