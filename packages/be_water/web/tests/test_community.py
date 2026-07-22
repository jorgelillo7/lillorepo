"""Community stats and achievements."""

from packages.be_water.web.community import build_community_stats
from packages.be_water.web.domain import Water


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
    catalog = [
        _water(
            f"w{i}",
            "jorgelillo",
            province,
            verified_fields=_NINE_FIELDS,
            photo="https://x/p.jpg",
            added_at="2026-07-01T10:00:00+00:00",
        )
        for i, province in enumerate(["Granada", "Toledo", "Cuenca", "Jaén", "Almería"])
    ]
    ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    # 5 waters * 9 fields = 45 verified, 5 photos, 5 provinces, 5 this month.
    assert {
        "Primera gota",
        "Ojo de halcón",
        "Cartógrafo",
        "Paparazzi",
        "Racha del mes",
    } <= names
    assert "Manantial andante" not in names  # needs 10 waters
    assert "Fuente inagotable" not in names  # needs 25 waters
    assert "Con gas" not in names  # no sparkling water added


def test_con_gas_and_higher_water_count_tiers():
    catalog = [_water(f"w{i}", "jorgelillo", "Granada") for i in range(10)] + [
        _water("sparkly", "jorgelillo", "Granada", sparkling=True)
    ]
    ranking = build_community_stats(catalog, "2026-07")
    names = {b["name"] for b in ranking[0]["badges"]}
    assert "Manantial andante" in names  # 11 waters >= 10
    assert "Fuente inagotable" not in names  # needs 25
    assert "Con gas" in names
