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
