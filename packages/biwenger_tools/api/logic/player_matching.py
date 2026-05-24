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
}


def normalize_name(name: str) -> str:
    """Normalise a name: lowercase, accent-stripped, trimmed."""
    return unidecode(name.lower().strip())


def build_jp_index(jp_players: list[dict]) -> dict:
    """Build lookup indexes over a JP player list to speed up matching.

    Returns a dict with two keys:
      - 'by_name': normalised name → JP player
      - 'by_slug': normalised slug → JP player (fallback)
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
    return {"by_name": by_name, "by_slug": by_slug}


def find_player_match(biwenger_name: str, jp_index: dict) -> dict | None:
    """Find the JP player that matches the given Biwenger name.

    Tries in order:
      1. Exact match on the normalised name.
      2. Manual override (PLAYER_NAME_MAPPINGS).
      3. Match by slug.
      4. Automatic transformations (last name, first name, "i. last").
      5. Token-subset match.

    Returns the JP player dict, or None if nothing matches.
    """
    by_name = jp_index["by_name"]
    by_slug = jp_index["by_slug"]
    norm = normalize_name(biwenger_name)

    if norm in by_name:
        return by_name[norm]

    if norm in PLAYER_NAME_MAPPINGS:
        mapped = PLAYER_NAME_MAPPINGS[norm]
        if mapped in by_name:
            return by_name[mapped]

    if norm in by_slug:
        return by_slug[norm]

    # Slugs typically have no spaces; try the no-space variant too.
    no_spaces = norm.replace(" ", "")
    if no_spaces in by_slug:
        return by_slug[no_spaces]

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
    for jp_norm, jp_player in by_name.items():
        if parts_set and parts_set.issubset(set(jp_norm.split())):
            return jp_player

    return None
