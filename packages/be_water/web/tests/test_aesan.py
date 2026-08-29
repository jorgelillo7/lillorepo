"""Tests for the AESAN registry lookups (coverage + pending list)."""

from unittest.mock import patch

from packages.be_water.web import aesan

# A registry where one uncovered brand ("Font Vella") spans two springs — the
# exact shape that made the pending count drift from the coverage count.
_REGISTRY = [
    {"name": "Bezoya", "spring": "Bezoya", "place": "x", "province": "Segovia"},
    {"name": "Font Vella", "spring": "Sacalm", "place": "a", "province": "Girona"},
    {"name": "Font Vella", "spring": "Sigüenza", "place": "b", "province": "GU"},
    {"name": "Lanjarón", "spring": "Salud", "place": "c", "province": "Granada"},
]


def _with_registry():
    return patch.object(aesan, "AESAN_WATERS", _REGISTRY)


def test_coverage_separates_distinct_names_from_registry_rows():
    """The two numbers are not interchangeable and the public pages state
    both. "España reconoce oficialmente N aguas" is a factual claim: N is the
    distinct commercial names, while the registry has more rows because a
    multi-spring brand is listed once per spring."""
    with _with_registry():
        summary = aesan.coverage(["Bezoya"])
    assert summary == {"total": 3, "covered": 1, "entries": 4}
    assert summary["entries"] > summary["total"], "Font Vella spans two springs"


def test_pending_dedupes_multi_spring_brand():
    with _with_registry():
        pending = aesan.pending_waters(["Bezoya"])
    names = [e["name"] for e in pending]
    assert names.count("Font Vella") == 1  # two springs collapse to one row


def test_pending_length_matches_coverage_gap():
    """The invariant the UI relies on: 'quedan N' (total - covered) must equal
    'ver las N pendientes' (len of the pending list)."""
    with _with_registry():
        summary = aesan.coverage(["Bezoya"])
        pending = aesan.pending_waters(["Bezoya"])
    assert len(pending) == summary["total"] - summary["covered"]
