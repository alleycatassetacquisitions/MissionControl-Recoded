"""Tests for GET /status."""
from fastapi.testclient import TestClient

from chrony_ops import FakeChronyOps
from main import set_ops
from models import SourceRow


def test_status_requires_auth(client: TestClient):
    resp = client.get("/status")
    assert resp.status_code == 401


def test_status_offline_public(client: TestClient, auth_headers: dict[str, str]):
    resp = client.get("/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["public_ntp"] == "unavailable"
    assert body["serving"] is True
    assert body["stratum"] == 10
    assert "iso" in body
    assert "unix" in body


def test_status_public_reachable(client: TestClient, auth_headers: dict[str, str]):
    set_ops(
        FakeChronyOps(
            public_ntp="reachable",
            stratum=3,
            reference="pool.ntp.org",
            sources=[
                SourceRow(name="pool.ntp.org", mode="*", stratum=2, state="reachable")
            ],
        )
    )
    resp = client.get("/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["public_ntp"] == "reachable"
    assert body["stratum"] == 3
    assert body["sources"][0]["name"] == "pool.ntp.org"
