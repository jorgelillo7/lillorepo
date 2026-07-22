"""Community stats and achievements — computed, never stored.

Badges are pure functions of a contributor's stats, so adding one is a
single entry in ACHIEVEMENTS and history rewrites itself for free.
"""

from packages.be_water.web.domain import Water

# (emoji, name, description, predicate over a stats dict)
ACHIEVEMENTS = [
    (
        "💧",
        "Primera gota",
        "Añadió su primera agua al catálogo",
        lambda s: s["waters_added"] >= 1,
    ),
    (
        "🦅",
        "Ojo de halcón",
        "25+ valores confirmados de etiqueta",
        lambda s: s["fields_verified"] >= 25,
    ),
    (
        "🗺️",
        "Cartógrafo",
        "Aguas de 3+ provincias distintas",
        lambda s: len(s["provinces"]) >= 3,
    ),
    (
        "📸",
        "Paparazzi",
        "5+ botellas fotografiadas",
        lambda s: s["waters_with_photo"] >= 5,
    ),
    (
        "🚰",
        "Manantial andante",
        "10+ aguas añadidas",
        lambda s: s["waters_added"] >= 10,
    ),
    (
        "🌊",
        "Fuente inagotable",
        "25+ aguas añadidas",
        lambda s: s["waters_added"] >= 25,
    ),
    (
        "🫧",
        "Con gas",
        "Añadió su primera agua con gas",
        lambda s: s["sparkling_added"] >= 1,
    ),
    (
        "🔥",
        "Racha del mes",
        "3+ aguas añadidas este mes",
        lambda s: s["month_waters"] >= 3,
    ),
]


def build_community_stats(catalog: list[Water], month_prefix: str) -> list[dict]:
    """Per-contributor stats (seed excluded), ranked by contribution score.

    `month_prefix` is "YYYY-MM" — used for the monthly counters over
    `added_at`. Score = 2 * waters added + fields verified. A single water
    add typically brings several verified fields with it (labels have
    5-9 declared minerals), so weighing them 1:1 let verification dwarf
    the rarer, harder act of adding a brand new water; doubling the water
    weight instead of halving the field weight keeps the score integer.
    """
    by_user: dict[str, dict] = {}
    for water in catalog:
        contributor = (water.added_by or "").strip().lower()
        if not contributor or contributor == "seed":
            continue
        stats = by_user.setdefault(
            contributor,
            {
                "nickname": contributor,
                "waters_added": 0,
                "fields_verified": 0,
                "waters_with_photo": 0,
                "provinces": set(),
                "sparkling_added": 0,
                "month_waters": 0,
                "month_fields": 0,
            },
        )
        stats["waters_added"] += 1
        stats["fields_verified"] += len(water.verified_fields)
        if water.photo_url:
            stats["waters_with_photo"] += 1
        if water.province:
            stats["provinces"].add(water.province)
        if water.sparkling:
            stats["sparkling_added"] += 1
        if water.added_at and water.added_at.startswith(month_prefix):
            stats["month_waters"] += 1
            stats["month_fields"] += len(water.verified_fields)

    ranking = []
    for stats in by_user.values():
        stats["score"] = 2 * stats["waters_added"] + stats["fields_verified"]
        stats["month_score"] = 2 * stats["month_waters"] + stats["month_fields"]
        stats["badges"] = [
            {"emoji": emoji, "name": name, "description": description}
            for emoji, name, description, predicate in ACHIEVEMENTS
            if predicate(stats)
        ]
        ranking.append(stats)
    ranking.sort(key=lambda s: (-s["score"], s["nickname"]))
    return ranking
