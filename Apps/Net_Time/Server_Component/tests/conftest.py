"""Pytest configuration for Net Time server tests.

Run from Apps/Net_Time/Server_Component/:

    pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from fastapi.testclient import TestClient

from chrony_ops import FakeChronyOps
from main import app, set_api_token, set_ops

TEST_TOKEN = "test-net-time-token"


@pytest.fixture(autouse=True)
def reset_ops():
    fake = FakeChronyOps(public_ntp="unavailable", stratum=10, reference="LOCAL")
    set_ops(fake)
    set_api_token(TEST_TOKEN)
    yield fake
    set_api_token("")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
