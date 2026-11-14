"""Unit tests for desired-first playback nudge arbitration (no broker)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLAYER = Path(__file__).resolve().parents[1] / "alleycattv_player"
if str(_PLAYER) not in sys.path:
    sys.path.insert(0, str(_PLAYER))

from mqtt_handler import drop_playback_nudge  # noqa: E402


@pytest.mark.parametrize(
    ("action", "until", "now", "expected"),
    [
        ("play", 100.0, 99.0, True),
        ("stop", 100.0, 99.0, True),
        ("volume", 100.0, 99.0, True),
        ("play", 100.0, 100.0, False),
        ("play", 100.0, 101.0, False),
        ("interrupt", 100.0, 99.0, False),
        ("reload", 100.0, 99.0, False),
        ("cache_purge", 100.0, 99.0, False),
    ],
)
def test_drop_playback_nudge(action, until, now, expected):
    assert drop_playback_nudge(action, until=until, now=now) is expected
