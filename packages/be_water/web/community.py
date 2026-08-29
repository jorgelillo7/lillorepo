"""Community stats and achievements — computed, never stored.

Badges are pure functions of a contributor's stats, so adding one is a
single entry in ACHIEVEMENTS and history rewrites itself for free.

Thresholds are set to be *worked for*. A catalog of 46 fichas made the old
ones reachable in an afternoon, and a badge everybody has says nothing about
anybody. The ceiling moved when compositions became a dated series: a water
is no longer one contribution but as many as it has been measured, so the
scale is now roughly 150 waters × N analyses rather than 150 full stop.
"""

from packages.be_water.web import aesan
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
        "50+ valores confirmados de etiqueta",
        lambda s: s["fields_verified"] >= 50,
    ),
    (
        "🗺️",
        "Cartógrafo",
        "Aguas de 6+ provincias distintas",
        lambda s: len(s["provinces"]) >= 6,
    ),
    (
        "📸",
        "Paparazzi",
        "12+ botellas fotografiadas",
        lambda s: s["waters_with_photo"] >= 12,
    ),
    (
        "🚰",
        "Manantial andante",
        "20+ aguas añadidas",
        lambda s: s["waters_added"] >= 20,
    ),
    (
        "🌊",
        "Fuente inagotable",
        "50+ aguas añadidas",
        lambda s: s["waters_added"] >= 50,
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
        "5+ contribuciones este mes",
        lambda s: s["month_waters"] + s["month_past_analyses"] >= 5,
    ),
    (
        "🧭",
        "Explorador",
        "Añadió un agua fuera del registro oficial AESAN",
        lambda s: s["off_registry_added"] >= 1,
    ),
    (
        "🕰️",
        "Segunda opinión",
        "Dio a un agua un análisis que no tenía",
        lambda s: s["past_analyses"] >= 1,
    ),
    (
        "📚",
        "Archivero",
        "Convirtió 5 aguas en una serie de mediciones",
        lambda s: s["histories_deepened"] >= 5,
    ),
    (
        "🏺",
        "Arqueólogo",
        "15+ análisis rescatados de años que nadie había documentado",
        lambda s: s["past_analyses"] >= 15,
    ),
]


def _blank(nickname: str) -> dict:
    return {
        "nickname": nickname,
        "waters_added": 0,
        "fields_verified": 0,
        "waters_with_photo": 0,
        "provinces": set(),
        "sparkling_added": 0,
        "off_registry_added": 0,
        "past_analyses": 0,
        "deepened": set(),
        "month_waters": 0,
        "month_fields": 0,
        "month_past_analyses": 0,
    }


def build_community_stats(
    catalog: list[Water], month_prefix: str, analyses: list[dict] | None = None
) -> list[dict]:
    """Per-contributor stats (seed excluded), ranked by contribution score.

    Counts **acts**, not the catalog's current state. That distinction is the
    whole of this function: a water's composition is a dated series now, and
    an older analysis deliberately never touches the ficha — so photographing
    a label from 2020, the work the series exists to invite, scored zero while
    the ranking read `waters` alone.

    A dated water's current entry *is* the act of adding it, so only analyses
    on some **other** date count separately; otherwise adding a water would
    pay twice. Confirmed fields are counted where the ✓ actually lives — in
    the entry that earned it — falling back to the ficha for the undated
    three quarters of the catalog, which have no entry at all.

    `month_prefix` is "YYYY-MM", over `added_at`. Score is
    `2 * waters + 2 * past analyses + fields`: a label from a year nobody had
    documented is worth what a new water is worth, because it is the same act
    — someone with a bottle in hand — and it is the scarcer of the two once
    the catalog fills up.
    """
    by_user: dict[str, dict] = {}
    dated = {w.id: w.analysis_date for w in catalog if w.analysis_date}
    per_water: dict[str, int] = {}
    for entry in analyses or []:
        per_water[entry.get("water_id")] = per_water.get(entry.get("water_id"), 0) + 1

    for entry in analyses or []:
        contributor = (entry.get("added_by") or "").strip().lower()
        if not contributor or contributor == "seed":
            continue
        stats = by_user.setdefault(contributor, _blank(contributor))
        stats["fields_verified"] += len(entry.get("verified_fields") or [])
        water_id = entry.get("water_id")
        if entry.get("analysis_date") == dated.get(water_id):
            continue  # the water's current composition: that was the add
        stats["past_analyses"] += 1
        if per_water.get(water_id, 0) > 1:
            stats["deepened"].add(water_id)
        if (entry.get("added_at") or "").startswith(month_prefix):
            stats["month_past_analyses"] += 1

    for water in catalog:
        contributor = (water.added_by or "").strip().lower()
        if not contributor or contributor == "seed":
            continue
        stats = by_user.setdefault(contributor, _blank(contributor))
        stats["waters_added"] += 1
        if not water.analysis_date:
            stats["fields_verified"] += len(water.verified_fields)
        if water.photo_url:
            stats["waters_with_photo"] += 1
        if water.province:
            stats["provinces"].add(water.province)
        if water.sparkling:
            stats["sparkling_added"] += 1
        if not (
            aesan.registry_matches(water.name) or aesan.registry_matches(water.brand)
        ):
            stats["off_registry_added"] += 1
        if water.added_at and water.added_at.startswith(month_prefix):
            stats["month_waters"] += 1
            stats["month_fields"] += len(water.verified_fields)

    ranking = []
    for stats in by_user.values():
        stats["histories_deepened"] = len(stats["deepened"])
        stats["score"] = (
            2 * stats["waters_added"]
            + 2 * stats["past_analyses"]
            + stats["fields_verified"]
        )
        stats["month_score"] = (
            2 * stats["month_waters"]
            + 2 * stats["month_past_analyses"]
            + stats["month_fields"]
        )
        stats["badges"] = [
            {"emoji": emoji, "name": name, "description": description}
            for emoji, name, description, predicate in ACHIEVEMENTS
            if predicate(stats)
        ]
        ranking.append(stats)
    ranking.sort(key=lambda s: (-s["score"], s["nickname"]))
    return ranking
