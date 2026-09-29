"""Tests for player_normalize — Central legacy keys → canonical fields."""
from __future__ import annotations

import pytest

from player_normalize import (
    normalize_player,
    normalize_role,
    to_central_create_body,
    to_central_write_body,
)


def test_normalize_allegiance_to_neocorp():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "allegiance": "Helix",
            "mode": "hunter",
            "faction": "Phoenix",
            "neo_id": "n1",
        }
    )
    assert out["neocorp"] == "helix"
    assert out["role"] == "hunter"
    assert out["faction"] == "Phoenix"
    assert out["neo_id"] == "n1"


def test_normalize_hunter_int_to_role():
    assert normalize_role({"hunter": 1}) == "hunter"
    assert normalize_role({"hunter": 2}) == "bounty"


def test_normalize_mode_preferred_over_hunter():
    assert normalize_role({"mode": "bounty", "hunter": 1}) == "bounty"


def test_normalize_already_canonical():
    out = normalize_player(
        {
            "id": "p2",
            "name": "Bob",
            "role": "bounty",
            "neocorp": "endline",
            "faction": "",
            "neo_id": "",
        }
    )
    assert out["role"] == "bounty"
    assert out["neocorp"] == "endline"


def test_normalize_missing_id_or_name_raises():
    with pytest.raises(ValueError):
        normalize_player({"name": "NoId"})
    with pytest.raises(ValueError):
        normalize_player({"id": "x"})


def test_to_central_write_body_maps_legacy_keys():
    body = to_central_write_body(
        name="Alice", role="bounty", neocorp="Helix", faction="F", neo_id="n"
    )
    assert body["allegiance"] == "helix"
    assert body["hunter"] == 2
    assert body["role"] == "bounty"
    assert body["name"] == "Alice"


def test_to_central_create_defaults_freelancer():
    body = to_central_create_body(name="New")
    assert body["allegiance"] == "freelancer"
    assert body["hunter"] == 1
