"""Pytest configuration for Master Control Server tests.

Run pytest from Apps/Master_Control_Server/Server_Component/ so the
package root is importable.

    cd Apps/Master_Control_Server/Server_Component
    pytest
"""
import sys
from pathlib import Path

# Make the Server_Component package importable.
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
from fastapi.testclient import TestClient

from main import app, _config

# Token used in every test that needs auth.
TEST_TOKEN = "test-secret-token"


@pytest.fixture(autouse=True)
def reset_config():
    """Reset MCS runtime config before each test to a known state."""
    _config["central_primary"] = "http://primary.example.com"
    _config["central_secondary"] = "http://secondary.example.com"
    _config["api_token"] = TEST_TOKEN
    yield
    # restore to empty after test
    _config["central_primary"] = ""
    _config["central_secondary"] = ""
    _config["api_token"] = ""


@pytest.fixture
def client() -> TestClient:
    """Synchronous FastAPI TestClient."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
