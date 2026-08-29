"""Community stats and achievements."""

from unittest.mock import patch

from packages.be_water.web.community import build_community_stats
from packages.be_water.web.domain import Water

_FAKE_REGISTRY = [
    {"name": "Font Nova", "spring": "", "place": "", "province": "Girona"}
]


def _water(
    wid,
    added_by,
    province,
    verified_fields=(),
    photo=None,
    added_at=None,
    sparkling=False,
):
    return Water(
        id=wid,
        name=wid,
        brand=wid,
        spring="",
        province=province,
        community="",
        added_by=added_by,
        added_at=added_at,
        verified_fields=list(verified_fields),
        photo_url=photo,
        minerals={"tds": 100},
        sparkling=sparkling,
    )


def test_seed_waters_do_not_rank():
    ranking = build_community_stats(
        [_water("a", "seed", "Cuenca"), _water("b", "", "Jaén")], "2026-07"
    )
    assert ranking == []


def test_scores_and_ranking_order():
    catalog = [
        _water("a", "jorgelillo", "Granada", verified_fields=["tds", "calcium"]),
        _water("b", "jorgelillo", "Toledo"),
        _water("c", "manu", "Cuenca"),
    ]
    ranking = build_community_stats(catalog, "2026-07")
    assert [s["nickname"] for s in ranking] == ["jorgelillo", "manu"]
    assert ranking[0]["score"] == 6  # 2*2 waters + 2 verified fields
    assert ranking[1]["score"] == 2  # 2*1 waters + 0 verified fields


def test_monthly_counters_use_added_at():
    catalog = [
        _water("a", "manu", "Cuenca", added_at="2026-07-18T10:00:00+00:00"),
        _water("b", "manu", "Jaén", added_at="2026-06-02T10:00:00+00:00"),
    ]
    ranking = build_community_stats(catalog, "2026-07")
    assert ranking[0]["waters_added"] == 2
    assert ranking[0]["month_waters"] == 1


_NINE_FIELDS = [
    "tds",
    "sodium",
    "calcium",
    "magnesium",
    "potassium",
    "bicarbonate",
    "chloride",
    "sulfate",
    "nitrate",
]


def test_achievements_fire_on_thresholds():
    """The thresholds are meant to be worked for: seven waters, all
    photographed, nine fields each, across seven provinces, in one month —
    and that is still short of the water-count tiers."""
    provinces = ["Granada", "Toledo", "Cuenca", "Jaén", "Almería", "Lugo", "Soria"]
    catalog = [
        _water(
            f"w{i}",
            "jorgelillo",
            province,
            verified_fields=_NINE_FIELDS,
            photo="https://x/p.jpg",
            added_at="2026-07-01T10:00:00+00:00",
        )
        for i, province in enumerate(provinces)
    ]
    ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    # 7 waters * 9 fields = 63 verified, 7 photos, 7 provinces, 7 this month.
    assert {
        "Primera gota",
        "Ojo de halcón",
        "Cartógrafo",
        "Racha del mes",
    } <= names
    assert "Paparazzi" not in names  # needs 12 photographed
    assert "Manantial andante" not in names  # needs 20 waters
    assert "Fuente inagotable" not in names  # needs 50 waters
    assert "Con gas" not in names  # no sparkling water added
    assert "Segunda opinión" not in names  # no analysis beyond a water's own


def test_con_gas_and_higher_water_count_tiers():
    catalog = [_water(f"w{i}", "jorgelillo", "Granada") for i in range(20)] + [
        _water("sparkly", "jorgelillo", "Granada", sparkling=True)
    ]
    ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    assert "Manantial andante" in names  # 21 waters >= 20
    assert "Fuente inagotable" not in names  # needs 50
    assert "Con gas" in names


def _entry(water_id, date, added_by, fields=(), added_at=None):
    return {
        "water_id": water_id,
        "analysis_date": date,
        "added_by": added_by,
        "verified_fields": list(fields),
        "added_at": added_at,
    }


def test_rescuing_an_analysis_a_water_lacked_is_worth_adding_one():
    """The reason this function had to change.

    An older analysis deliberately never touches the ficha, and the ranking
    read `waters` alone — so photographing a label from 2020, the work the
    dated series exists to invite, moved the score by nothing at all.
    """
    catalog = [_water("penaclara", "jorgelillo", "La Rioja")]
    catalog[0].analysis_date = "2025-02"
    analyses = [
        _entry("penaclara", "2025-02", "jorgelillo", _NINE_FIELDS),
        _entry("penaclara", "2024-01", "bea", _NINE_FIELDS),
    ]

    ranking = build_community_stats(catalog, "2026-07", analyses)
    by_name = {s["nickname"]: s for s in ranking}

    # bea added no water at all, and is on the board for the year she rescued.
    assert by_name["bea"]["past_analyses"] == 1
    assert by_name["bea"]["score"] == 2 + len(_NINE_FIELDS)
    assert "Segunda opinión" in {b["name"] for b in by_name["bea"]["badges"]}


def test_a_water_is_not_paid_twice_for_its_own_composition():
    """Every dated water has an entry for the composition it currently shows.
    Counting that as a separate act would pay two points for one bottle."""
    catalog = [_water("penaclara", "jorgelillo", "La Rioja")]
    catalog[0].analysis_date = "2025-02"
    analyses = [_entry("penaclara", "2025-02", "jorgelillo", ["tds"])]

    stats = build_community_stats(catalog, "2026-07", analyses)[0]

    assert stats["past_analyses"] == 0
    assert stats["score"] == 2 + 1, "un agua y su campo, no un agua y un análisis"


def test_the_field_count_does_not_double_when_a_water_is_dated():
    """The ✓ lives in the entry that earned it; the ficha carries the union of
    every label ever photographed. Counting both would inflate the score of
    exactly the contributors who document a water most."""
    catalog = [_water("a", "jorgelillo", "Granada", verified_fields=_NINE_FIELDS)]
    catalog[0].analysis_date = "2025-02"
    analyses = [_entry("a", "2025-02", "jorgelillo", _NINE_FIELDS)]

    stats = build_community_stats(catalog, "2026-07", analyses)[0]

    assert stats["fields_verified"] == len(_NINE_FIELDS)


def test_an_undated_water_still_counts_its_fields():
    """Three quarters of the catalog has no analysis date and so no entry —
    for those the ficha is the only record there is."""
    catalog = [_water("a", "jorgelillo", "Granada", verified_fields=["tds", "sodium"])]

    stats = build_community_stats(catalog, "2026-07", [])[0]

    assert stats["fields_verified"] == 2


def test_archivero_counts_waters_turned_into_a_series_not_analyses():
    """Five analyses on one water is one history deepened, not five."""
    catalog = []
    analyses = []
    for i in range(5):
        water = _water(f"w{i}", "jorgelillo", "Granada")
        water.analysis_date = "2025-02"
        catalog.append(water)
        analyses.append(_entry(f"w{i}", "2025-02", "jorgelillo"))
    analyses += [_entry("w0", f"20{10 + i}", "bea") for i in range(5)]

    ranking = build_community_stats(catalog, "2026-07", analyses)
    bea = {s["nickname"]: s for s in ranking}["bea"]

    assert bea["past_analyses"] == 5
    assert bea["histories_deepened"] == 1, "un agua, por muchas mediciones que tenga"
    assert "Archivero" not in {b["name"] for b in bea["badges"]}


def test_explorador_fires_for_water_outside_aesan_registry():
    catalog = [_water("Agua Rara", "jorgelillo", "Cuenca")]
    with patch("packages.be_water.web.community.aesan.AESAN_WATERS", _FAKE_REGISTRY):
        ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    assert "Explorador" in names


def test_explorador_does_not_fire_for_water_matching_aesan_registry():
    catalog = [_water("Font Nova", "jorgelillo", "Girona")]
    with patch("packages.be_water.web.community.aesan.AESAN_WATERS", _FAKE_REGISTRY):
        ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    assert "Explorador" not in names
