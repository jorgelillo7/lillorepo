from collections import defaultdict

from unidecode import unidecode

# Hand-maintained Biwenger → JP name overrides for the cases where no
# automatic strategy matches (completely different spellings, nicknames,
# aliases). Keys are normalised (lowercase, accents stripped).
PLAYER_NAME_MAPPINGS = {
    # Vinicius en Biwenger ↔ "Vini Jr" en JP
    "vinicius jr": "vini jr",
    "vinicius junior": "vini jr",
    # Inversiones / variaciones conocidas históricas
    "sancet": "oihan sancet",
    "javi hernandez": "javier hernandez",
    "javier rueda": "javi rueda",
    "brugue": "brugui",
    "ricardo rodriguez": "r. rodriguez",
    "matias moreno": "m. moreno",
    # JP short-names the automatic strategies can't derive from the Biwenger
    # full name (confirmed against the Automanager list).
    "de la fuente": "dela",
    "juan cruz diaz": "j. cruz",
    "de tomas": "rdt",  # Raúl De Tomás
}


def normalize_name(name: str) -> str:
    """Normalise a name: lowercase, accent-stripped, trimmed."""
    return unidecode(name.lower().strip())


def build_jp_index(
    jp_players: list[dict], biwenger_names: list[str] | None = None
) -> dict:
    """Build lookup indexes over a JP player list to speed up matching.

    Returns a dict with:
      - 'by_name': normalised name → JP player
      - 'by_slug': normalised slug → JP player (fallback)
      - 'ambiguous_loose_targets': `id()` of JP players that the loose
        ladder in `find_player_match` would otherwise hand to 2+ different
        Biwenger players (e.g. "Rubén García", "Rubén López" and "Rubén
        Sánchez" all reducing to the single JP mononym "Rubén"). Computed
        only when `biwenger_names` covers the full roster; empty otherwise,
        which disables the cross-roster check but leaves per-call matching
        (including the token-subset uniqueness gate) unaffected.
    """
    by_name: dict[str, dict] = {}
    by_slug: dict[str, dict] = {}
    for p in jp_players:
        name = p.get("name") or ""
        slug = p.get("slug") or ""
        if name:
            by_name[normalize_name(name)] = p
        if slug:
            by_slug[normalize_name(slug)] = p
    return {
        "by_name": by_name,
        "by_slug": by_slug,
        "ambiguous_loose_targets": _find_ambiguous_loose_targets(
            biwenger_names or [], by_name, by_slug
        ),
    }


def _loose_candidate(norm: str, by_name: dict) -> dict | None:
    """Surname / first name / initial+surname / token-subset ladder.

    The first three tiers are single-key lookups, so at most one JP
    player can ever qualify per call — real ambiguity there only shows up
    across the whole Biwenger roster (see `_find_ambiguous_loose_targets`).
    The token-subset tier scans the whole index, so it can find several
    qualifying JP players within a single call; it is accepted only when
    exactly one does.
    """
    parts = norm.split()
    if len(parts) > 1:
        last = parts[-1]
        if last in by_name:
            return by_name[last]

        first = parts[0]
        if first in by_name:
            return by_name[first]

        initial_last = f"{parts[0][0]}. {parts[-1]}"
        if initial_last in by_name:
            return by_name[initial_last]

    parts_set = set(parts)
    if not parts_set:
        return None
    matches = [
        jp_player
        for jp_norm, jp_player in by_name.items()
        if parts_set.issubset(set(jp_norm.split()))
    ]
    return matches[0] if len(matches) == 1 else None


def _safe_match(norm: str, by_name: dict, by_slug: dict) -> dict | None:
    """Exact/override/slug lookup only — mirrors the safe tiers of
    `find_player_match`, without ever falling through to the loose ladder."""
    if norm in by_name:
        return by_name[norm]
    mapped = PLAYER_NAME_MAPPINGS.get(norm)
    if mapped and mapped in by_name:
        return by_name[mapped]
    if norm in by_slug:
        return by_slug[norm]
    no_spaces = norm.replace(" ", "")
    if no_spaces in by_slug:
        return by_slug[no_spaces]
    return None


def _find_ambiguous_loose_targets(
    biwenger_names: list[str], by_name: dict, by_slug: dict
) -> set[int]:
    """JP player identities the loose ladder must not resolve on its own.

    A target is blocked when either:
      - 2+ Biwenger names would independently reduce to it through the
        loose ladder (e.g. "Rubén García" and "Rubén López" both landing
        on the JP mononym "Rubén"), or
      - it is already claimed by some *other* Biwenger name through a safe
        (exact/override/slug) match — a loose fallback must never hand out
        a JP record that rightfully belongs to someone else, even if it
        looks like the only loose contender.
    """
    safely_claimed: set[int] = set()
    loose_claimants: dict[int, set[str]] = defaultdict(set)
    for bw_name in biwenger_names:
        norm = normalize_name(bw_name)
        safe = _safe_match(norm, by_name, by_slug)
        if safe is not None:
            safely_claimed.add(id(safe))
            continue
        candidate = _loose_candidate(norm, by_name)
        if candidate is not None:
            loose_claimants[id(candidate)].add(norm)
    ambiguous = {jp_id for jp_id, names in loose_claimants.items() if len(names) > 1}
    ambiguous |= safely_claimed & set(loose_claimants)
    return ambiguous


def find_player_match(biwenger_name: str, jp_index: dict) -> dict | None:
    """Find the JP player that matches the given Biwenger name.

    Tries in order:
      1. Exact match on the normalised name.
      2. Manual override (PLAYER_NAME_MAPPINGS).
      3. Match by slug.
      4. Automatic transformations (last name, first name, "i. last").
      5. Token-subset match.

    Tiers 4-5 only resolve when unique: a token-subset scan with more than
    one hit is rejected outright, and a single-key hit (surname / first
    name / initial+surname) is rejected if `build_jp_index` flagged it as
    claimed by more than one Biwenger player across the whole roster.

    Returns the JP player dict, or None if nothing matches — including when
    a loose match exists but is ambiguous. Callers already treat a missing
    JP player as "no data for this player" rather than an error.
    """
    by_name = jp_index["by_name"]
    by_slug = jp_index["by_slug"]
    norm = normalize_name(biwenger_name)

    safe = _safe_match(norm, by_name, by_slug)
    if safe is not None:
        return safe

    candidate = _loose_candidate(norm, by_name)
    if candidate is None:
        return None
    if id(candidate) in jp_index.get("ambiguous_loose_targets", ()):
        return None
    return candidate
