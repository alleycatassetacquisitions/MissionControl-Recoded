"""Unit-level tests for BGC helpers that do not need the HA fixture."""
from __future__ import annotations

import importlib

from custom_components.broadcast_group_controller.const import (
    DOMAIN,
    KIND_DOMAIN,
    KIND_TV,
    SERVICE_SET_BROADCAST_GROUP,
    SUPPORTED_KINDS,
)

bgc_mod = importlib.import_module(
    "custom_components.broadcast_group_controller"
)


def test_store_key():
    assert bgc_mod._store_key("tv", "pi-01") == "tv:pi-01"


def test_constants():
    assert DOMAIN == "broadcast_group_controller"
    assert KIND_TV in SUPPORTED_KINDS
    assert KIND_DOMAIN["tv"] == "alleycattv"
    assert SERVICE_SET_BROADCAST_GROUP == "set_broadcast_group"
