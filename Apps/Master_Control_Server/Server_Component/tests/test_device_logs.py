"""Tests for MCS GET /device-logs proxy."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

SAMPLE_LOGS = {
    "device_logs": [
        {
            "id": "d1",
            "device_mac": "aa:bb:cc:dd:ee:ff",
            "crash_number": 1,
            "uptime_ms": 1000,
            "received_at": "2026-01-01T00:00:00Z",
            "reset_reason": 3,
            "software_version": "1.0.0",
            "task_name": "main",
            "program_counter": None,
            "exception_cause": None,
        }
    ],
    "pagination": {"page": 1, "per_page": 20},
}


def test_device_logs_requires_auth(client: TestClient):
    resp = client.get("/device-logs")
    assert resp.status_code == 401


def test_device_logs_proxies_central(client: TestClient, auth_headers: dict):
    with patch(
        "main.fetch_device_logs",
        new=AsyncMock(return_value=(200, SAMPLE_LOGS)),
    ) as mock_fetch:
        resp = client.get("/device-logs?page=1&per_page=20", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["device_logs"]) == 1
    assert data["device_logs"][0]["device_mac"] == "aa:bb:cc:dd:ee:ff"
    assert data["pagination"] == {"page": 1, "per_page": 20}
    assert mock_fetch.await_args.kwargs["page"] == 1
    assert mock_fetch.await_args.kwargs["per_page"] == 20


def test_device_logs_central_error(client: TestClient, auth_headers: dict):
    with patch(
        "main.fetch_device_logs",
        new=AsyncMock(return_value=(500, "Database operation failed")),
    ):
        resp = client.get("/device-logs", headers=auth_headers)
    assert resp.status_code == 502
