"""Unit tests for HA-only affiliation default enrichment (no HA runtime)."""
from __future__ import annotations

import sys
from pathlib import Path

_ha_component_dir = Path(__file__).parent.parent
if str(_ha_component_dir) not in sys.path:
    sys.path.insert(0, str(_ha_component_dir))

from custom_components.game_master.affiliations import (  # noqa: E402
    enrich_catalog_with_defaults,
)


def test_enrich_attaches_valid_default():
    catalog = {
        "event_id": "evt-1",
        "categories": [
            {
                "id": "cat-allegiance",
                "name": "Allegiance",
                "affiliations": [
                    {"id": "a1", "name": "Endline"},
                    {"id": "a2", "name": "Freelancer"},
                ],
            }
        ],
    }
    defaults = {"evt-1": {"cat-allegiance": "a2"}}
    out = enrich_catalog_with_defaults(catalog, defaults)
    assert out["categories"][0]["default_affiliation_id"] == "a2"


def test_enrich_clears_stale_default():
    catalog = {
        "event_id": "evt-1",
        "categories": [
            {
                "id": "cat-allegiance",
                "name": "Allegiance",
                "affiliations": [{"id": "a1", "name": "Endline"}],
            }
        ],
    }
    defaults = {"evt-1": {"cat-allegiance": "missing-id"}}
    out = enrich_catalog_with_defaults(catalog, defaults)
    assert out["categories"][0]["default_affiliation_id"] is None


def test_enrich_ignores_other_events():
    catalog = {
        "event_id": "evt-2",
        "categories": [
            {
                "id": "cat-x",
                "name": "Faction",
                "affiliations": [{"id": "f1", "name": "Phoenix"}],
            }
        ],
    }
    defaults = {"evt-1": {"cat-x": "f1"}}
    out = enrich_catalog_with_defaults(catalog, defaults)
    assert out["categories"][0]["default_affiliation_id"] is None


def test_enrich_empty_event():
    catalog = {"event_id": None, "categories": []}
    out = enrich_catalog_with_defaults(catalog, {"evt-1": {"c": "a"}})
    assert out["categories"] == []
    assert out["event_id"] is None
