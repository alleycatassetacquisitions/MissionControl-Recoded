"""Unit tests for GBN HA helpers (no full hass fixture required on Windows)."""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

from custom_components.gbn.const import DOMAIN, KEY_GBN


def test_constants():
    assert DOMAIN == "gbn"
    assert KEY_GBN == "gbn"


def test_server_url_from_core_configurator():
    http_mod = importlib.import_module("custom_components.gbn.http")
    hass = MagicMock()
    with patch.object(http_mod, "get_url", return_value="http://gbn.local:8100/"):
        assert http_mod._server_url(hass) == "http://gbn.local:8100"


def test_server_url_fail_closed_when_empty():
    http_mod = importlib.import_module("custom_components.gbn.http")
    hass = MagicMock()
    with patch.object(http_mod, "get_url", return_value=""):
        assert http_mod._server_url(hass) is None


def test_proxy_view_paths():
    http_mod = importlib.import_module("custom_components.gbn.http")
    assert http_mod.GbnProxyView.url == "/api/gbn/proxy/{path:.*}"
    assert http_mod.GbnProxyView.requires_auth is True
