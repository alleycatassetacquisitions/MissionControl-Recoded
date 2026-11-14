"""Unit tests for GBN HA helpers (no full hass fixture required on Windows)."""
from __future__ import annotations

import importlib

from custom_components.gbn.const import DOMAIN, KEY_GBN


def test_constants():
    assert DOMAIN == "gbn"
    assert KEY_GBN == "gbn"


def test_proxy_view_paths():
    http_mod = importlib.import_module("custom_components.gbn.http")
    assert http_mod.GbnProxyView.url == "/api/gbn/proxy/{path:.*}"
    assert http_mod.GbnProxyView.requires_auth is True
