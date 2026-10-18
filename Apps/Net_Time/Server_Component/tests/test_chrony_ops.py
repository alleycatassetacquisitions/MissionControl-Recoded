"""Unit tests for chrony CSV parsing helpers."""
from chrony_ops import _parse_sources, _parse_tracking, _public_ntp_from_sources
from models import SourceRow


def test_parse_tracking():
    # ref, ref_mode, stratum, ...
    csv = "A1B2C3D4,1,3,0.000,0.001,0.002,0.003,0.004"
    ref, stratum = _parse_tracking(csv)
    assert ref == "A1B2C3D4"
    assert stratum == 3


def test_parse_sources_reachable():
    # Mode, State, Name, Stratum, Poll, Reach, ...
    csv = "^,*,pool.ntp.org,2,6,377,12,+0.001"
    rows = _parse_sources(csv)
    assert len(rows) == 1
    assert rows[0].name == "pool.ntp.org"
    assert rows[0].mode == "^/*"
    assert rows[0].stratum == 2
    assert rows[0].state == "reachable"


def test_parse_sources_local_clock():
    csv = "#,*,LOCL,10,6,377,0,0.0"
    rows = _parse_sources(csv)
    assert rows[0].state == "local"
    assert rows[0].name == "LOCL"


def test_public_ntp_from_local_only():
    sources = [SourceRow(name="LOCL", mode="#/*", stratum=10, state="local")]
    assert _public_ntp_from_sources(sources) == "unavailable"


def test_public_ntp_from_pool():
    sources = [
        SourceRow(name="pool.ntp.org", mode="^/*", stratum=2, state="reachable"),
    ]
    assert _public_ntp_from_sources(sources) == "reachable"


def test_public_ntp_fallback_from_tracking_stratum():
    """Stratum 3 + non-local ref ⇒ reachable even with empty sources list."""
    assert (
        _public_ntp_from_sources([], reference="A1B2C3D4", stratum=3) == "reachable"
    )


def test_public_ntp_local_stratum_stays_unavailable():
    assert (
        _public_ntp_from_sources([], reference="LOCAL", stratum=10) == "unavailable"
    )
