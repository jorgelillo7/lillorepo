"""Lookups over the AESAN snapshot.

The official registry carries identity only (commercial name, spring,
place) — never compositions. It powers the add-form prefill and the
sync coverage stat; it never creates catalog entries by itself.
"""

from unidecode import unidecode

from packages.be_water.web.aesan_snapshot import AESAN_WATERS


def _tokens(text: str) -> set:
    return set(unidecode(text or "").lower().replace("-", " ").split())


def registry_matches(name: str) -> list[dict]:
    """AESAN entries whose commercial name token-matches `name` (subset
    either way, accent-insensitive). Several entries → multi-spring brand."""
    tokens = _tokens(name)
    if not tokens:
        return []
    return [
        entry
        for entry in AESAN_WATERS
        if (t := _tokens(entry["name"])) and (tokens <= t or t <= tokens)
    ]


def _key(text: str) -> str:
    return unidecode(text or "").strip().lower()


def coverage(catalog_names) -> dict:
    """How much of the registry the given names cover (containment either
    way, accent-insensitive). White labels register under the producer's
    name and rightly don't match."""
    registry = {_key(e["name"]) for e in AESAN_WATERS}
    names = {_key(n) for n in catalog_names if n}
    covered = {r for r in registry if any(r in n or n in r for n in names)}
    return {"total": len(registry), "covered": len(covered)}


def pending_waters(catalog_names) -> list[dict]:
    """AESAN entries not matched by any catalog name — the public "still
    to catalogue" list, sorted by province then name for a scannable UI."""
    names = {_key(n) for n in catalog_names if n}
    pending = [
        entry
        for entry in AESAN_WATERS
        if not any(_key(entry["name"]) in n or n in _key(entry["name"]) for n in names)
    ]
    return sorted(pending, key=lambda e: (e["province"], e["name"]))
