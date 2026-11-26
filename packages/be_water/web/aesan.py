"""Lookups over the official registry snapshots.

Spain's table (`aesan_snapshot`) and every other EU and EEA country's
(`eu_snapshot`) carry identity only (commercial name, spring, place) — never
compositions. They power the add-form prefill, the coverage stat and the
"recognised by" line on a foreign ficha; they never create catalog entries.
"""

from unidecode import unidecode

from packages.be_water.web.aesan_snapshot import AESAN_WATERS
from packages.be_water.web.eu_snapshot import EU_WATERS


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


def foreign_matches(name: str, country: str | None = None) -> list[dict]:
    """Other countries' registry entries whose name token-matches `name`, as
    `registry_matches` does for Spain's; only `country`'s when one is given."""
    tokens = _tokens(name)
    if not tokens:
        return []
    return [
        entry
        for entry in EU_WATERS
        if (country is None or entry["country"] == country)
        and (t := _tokens(entry["name"]))
        and (tokens <= t or t <= tokens)
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
    # `total` counts distinct commercial names, `entries` the registry rows:
    # a brand with several springs is listed once per spring. The pages say
    # which is which, because "España reconoce N aguas" is a factual claim
    # and the two numbers are not interchangeable.
    return {
        "total": len(registry),
        "covered": len(covered),
        "entries": len(AESAN_WATERS),
    }


def pending_waters(catalog_names) -> list[dict]:
    """AESAN entries not matched by any catalog name — the public "still to
    catalogue" list, sorted by province then name for a scannable UI.

    Deduplicated by commercial name so the list length matches `coverage`,
    which counts unique names: the registry lists multi-spring brands (Font
    Vella, Cabreiroá…) once per spring, and counting rows here while counting
    names there made "quedan N por fichar" disagree with "ver las M pendientes".
    """
    names = {_key(n) for n in catalog_names if n}
    uncovered = sorted(
        (
            entry
            for entry in AESAN_WATERS
            if not any(
                _key(entry["name"]) in n or n in _key(entry["name"]) for n in names
            )
        ),
        key=lambda e: (e["province"], e["name"]),
    )
    seen = set()
    deduped = []
    for entry in uncovered:
        key = _key(entry["name"])
        if key not in seen:
            seen.add(key)
            deduped.append(entry)
    return deduped
