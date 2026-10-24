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


def test_config_empty_primary_does_not_overwrite(client: TestClient, auth_headers: dict):
    """An empty string for central_primary leaves the existing value in place."""
    _config["central_primary"] = "http://original.example.com"
    _config["central_secondary"] = "http://secondary.example.com"
    client.post(
        "/config",
        json={"central_primary": ""},
        headers=auth_headers,
    )
    assert _config["central_primary"] == "http://original.example.com"
    assert _config["central_secondary"] == "http://secondary.example.com"


def test_config_empty_secondary_clears(client: TestClient, auth_headers: dict):
    """Explicit empty central_secondary clears a dead mirror URL."""
    _config["central_secondary"] = "http://192.168.1.234:8090"
    resp = client.post(
        "/config",
        json={"central_secondary": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _config["central_secondary"] == ""


def test_config_omit_secondary_leaves_current(client: TestClient, auth_headers: dict):
    """Omitting central_secondary leaves the existing value."""
    _config["central_secondary"] = "http://keep-secondary.example.com"
    resp = client.post(
        "/config",
        json={"central_primary": "http://primary.new"},
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _config["central_primary"] == "http://primary.new"
    assert _config["central_secondary"] == "http://keep-secondary.example.com"


def test_config_no_body_fields_defaults_to_empty_strings(
    client: TestClient, auth_headers: dict
):
    """Omitting fields entirely is valid — they default to empty / None."""
    _config["central_primary"] = "http://existing.example.com"
    _config["central_secondary"] = "http://existing-sec.example.com"
    resp = client.post("/config", json={}, headers=auth_headers)
    assert resp.status_code == 204
    assert _config["central_primary"] == "http://existing.example.com"
    assert _config["central_secondary"] == "http://existing-sec.example.com"


def test_config_stores_peer_snapshot(client: TestClient, auth_headers: dict, monkeypatch):
    """Non-empty peer fields are stored; fan-out is invoked."""
    from main import _last_fanout, _peers

    calls: list[dict] = []

    async def _fake_fanout(*, api_token: str, peers: dict):
        calls.append({"api_token": api_token, "peers": dict(peers)})
        return {"gbn": {"ok": True, "status": 204}}

    monkeypatch.setattr("main.fanout_peers", _fake_fanout)
    resp = client.post(
        "/config",
        json={
            "mcs_url": "http://10.10.50.110:8700",
            "gbn_url": "http://10.10.50.112:8100",
            "net_time_url": "http://10.10.50.113:8720",
            "net_time_token": "nt-secret",
            "alleycattv_url": "http://10.10.50.114:8000",
            "host_clock_url": "http://10.10.50.205:8721",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 204
    assert _peers["mcs_url"] == "http://10.10.50.110:8700"
    assert _peers["gbn_url"] == "http://10.10.50.112:8100"
    assert _peers["host_clock_url"] == "http://10.10.50.205:8721"
    assert len(calls) == 1
    assert calls[0]["peers"]["gbn_url"] == "http://10.10.50.112:8100"
    assert _last_fanout == {"gbn": {"ok": True, "status": 204}}


def test_config_empty_peer_does_not_overwrite(
    client: TestClient, auth_headers: dict, monkeypatch
):
    from main import _peers

    _peers["gbn_url"] = "http://original-gbn:8100"

    async def _fake_fanout(*, api_token: str, peers: dict):
        return {}

    monkeypatch.setattr("main.fanout_peers", _fake_fanout)
    client.post(
        "/config",
        json={"gbn_url": "", "central_primary": "http://p.example"},
        headers=auth_headers,
    )
    assert _peers["gbn_url"] == "http://original-gbn:8100"


def test_config_status_requires_auth(client: TestClient):
    resp = client.get("/config/status")
    assert resp.status_code == 401


def test_config_status_returns_peers_and_fanout(
    client: TestClient, auth_headers: dict, monkeypatch
):
    from main import _peers

    async def _fake_fanout(*, api_token: str, peers: dict):
        return {
            "gbn": {"ok": True, "status": 204},
            "net_time": {"ok": False, "skipped": True, "reason": "net_time_url unset"},
        }

    monkeypatch.setattr("main.fanout_peers", _fake_fanout)
    client.post(
        "/config",
        json={
            "central_primary": "http://primary.new",
            "central_secondary": "",
            "mcs_url": "http://10.10.50.110:8700",
            "gbn_url": "http://10.10.50.187:8100",
            "net_time_token": "secret-token",
        },
        headers=auth_headers,
    )
    resp = client.get("/config/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["central_primary"] == "http://primary.new"
    assert body["central_secondary"] == ""
    assert body["peers"]["mcs_url"] == "http://10.10.50.110:8700"
    assert body["peers"]["gbn_url"] == "http://10.10.50.187:8100"
    assert body["peers"]["net_time_token"] == "set"
    assert "secret-token" not in resp.text
    assert body["last_fanout"]["gbn"]["ok"] is True
