"""Tests for POST /config.

The Registration HA integration calls this endpoint on every HA start and
whenever Core Configurator fires core_configurator_updated with
central_primary or central_secondary changed.
"""
from fastapi.testclient import TestClient

from main import _config


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_config_requires_auth(client: TestClient):
    resp = client.post("/config", json={"central_primary": "http://new.example.com"})
    assert resp.status_code == 401


def test_config_wrong_token_rejected(client: TestClient):
    resp = client.post(
        "/config",
        json={"central_primary": "http://new.example.com"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_config_updates_central_primary(client: TestClient, auth_headers: dict):
    resp = client.post(
        "/config",
        json={"central_primary": "http://new-primary.example.com", "central_secondary": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _config["central_primary"] == "http://new-primary.example.com"


def test_config_updates_central_secondary(client: TestClient, auth_headers: dict):
    resp = client.post(
        "/config",
        json={"central_primary": "", "central_secondary": "http://new-secondary.example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _config["central_secondary"] == "http://new-secondary.example.com"


def test_config_updates_both_urls(client: TestClient, auth_headers: dict):
    resp = client.post(
        "/config",
        json={
            "central_primary": "http://primary.new",
            "central_secondary": "http://secondary.new",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _config["central_primary"] == "http://primary.new"
    assert _config["central_secondary"] == "http://secondary.new"


def test_config_empty_string_does_not_overwrite(client: TestClient, auth_headers: dict):
    """An empty string for a URL leaves the existing value in place."""
    _config["central_primary"] = "http://original.example.com"
    client.post(
        "/config",
        json={"central_primary": "", "central_secondary": ""},
        headers=auth_headers,
    )
    assert _config["central_primary"] == "http://original.example.com"


def test_config_no_body_fields_defaults_to_empty_strings(
    client: TestClient, auth_headers: dict
):
    """Omitting fields entirely is valid — they default to empty string."""
    _config["central_primary"] = "http://existing.example.com"
    resp = client.post("/config", json={}, headers=auth_headers)
    assert resp.status_code == 204
    # Empty-string default does not overwrite
    assert _config["central_primary"] == "http://existing.example.com"
