"""Unit tests for `api/logic/recommendations.py`.

Covers `compute_dynamic_margin`, `_pick_top_per_position` and
`_format_telegram_text`. The candidate-pool helpers (`gather_rivals`,
`filter_affordable`) live in `clausulazo_candidates` and are tested
in `test_clausulazo_candidates.py`. HTTP wiring is in `test_routes.py`.
"""

from unittest.mock import MagicMock

from packages.biwenger_tools.api.logic import clausulazo_candidates as cands
from packages.biwenger_tools.api.logic import recommendations as recs


def _row(
    bw_id,
    name,
    pos,
    alt=None,
    sf=300,
    clause=10_000_000,
    clausulable=True,
    owner_gk_count=2,
):
    return {
        "bw_id": bw_id,
        "name": name,
        "position_id": pos,
        "alt_positions": alt or [],
        "owner": "Pepe",
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
        "Clausulable": "Sí" if clausulable else "No (5d)",
        "Cláusula": f"{clause / 1_000_000:.1f}M",
        "clause_value": clause,
        "clausulable_now": clausulable,
        "owner_gk_count": owner_gk_count,
    }


# --- compute_dynamic_margin ---


def test_compute_dynamic_margin_scales_with_cash():
    # cash ≤ 0 → minimum
    assert recs.compute_dynamic_margin(0) == 2_000_000
    assert recs.compute_dynamic_margin(-100) == 2_000_000
    # 40% of cash, rounded to nearest 500k, clamped [2M, 10M]
    assert recs.compute_dynamic_margin(5_000_000) == 2_000_000  # 0.4*5M=2M (floor)
    assert recs.compute_dynamic_margin(12_972_212) == 5_000_000  # ~5.19M → round 5.0
    assert recs.compute_dynamic_margin(20_000_000) == 8_000_000
    assert recs.compute_dynamic_margin(30_000_000) == 10_000_000  # cap
    assert recs.compute_dynamic_margin(100_000_000) == 10_000_000  # cap


# --- filter_affordable ---


def test_filter_affordable_excludes_my_players_and_locked_and_too_expensive():
    my_ids = {1}
    rows = [
        _row(1, "Mine", pos=2),  # excluded: mine
        _row(2, "Locked", pos=2, clausulable=False),  # excluded: locked
        _row(3, "Expensive", pos=2, clause=100_000_000),  # excluded: > target
        _row(4, "Cheap", pos=2, clause=20_000_000),  # included
        _row(5, "NoSF", pos=2, sf=0, clause=15_000_000),  # excluded: SF 0
    ]
    out = cands.filter_affordable(rows, my_ids, target=50_000_000)
    assert [r["bw_id"] for r in out] == [4]


def test_filter_affordable_excludes_rival_only_gk_house_rule():
    """House rule: never clauselazo a rival's only goalkeeper. Biwenger
    technically allows it but the league agreed leaving someone with zero
    GKs is unsportsmanlike. The same rule does NOT apply to outfield
    positions — a rival's only FWD is fair game."""
    rows = [
        # Sole GK at the rival → filtered out by the house rule.
        _row(100, "Dituro", pos=1, owner_gk_count=1, clause=8_000_000, sf=350),
        # Rival with a backup GK → recommendable.
        _row(101, "OtherGk", pos=1, owner_gk_count=2, clause=9_000_000, sf=350),
        # The rule must not bleed into outfield: sole striker stays included.
        _row(102, "SoleFwd", pos=4, owner_gk_count=1, clause=10_000_000, sf=400),
    ]
    out = cands.filter_affordable(rows, my_ids=set(), target=50_000_000)
    assert [r["bw_id"] for r in out] == [101, 102]


# --- gather_rivals ---


def test_gather_rivals_annotates_owner_gk_count_and_user_id(monkeypatch):
    """`gather_rivals` must tag every rival row with the owner's GK count
    (for the house rule) and the owner_user_id (needed by emergency to
    fill `place_clausulazo`'s `to=<seller>` field). Two managers, one
    with 1 GK, one with 2."""
    biwenger = MagicMock()
    biwenger.user_id = 0
    biwenger.get_league_users.return_value = {1: "Ana", 2: "Beto"}
    biwenger.get_manager_squad.side_effect = lambda url, mgr_id: {
        1: [{"id": 11}, {"id": 12}],  # Ana: 1 GK + 1 DEF
        2: [{"id": 21}, {"id": 22}, {"id": 23}],  # Beto: 2 GK + 1 FWD
    }[mgr_id]
    biwenger_players = {
        11: {
            "id": 11,
            "name": "Ana-Gk",
            "position": 1,
            "price": 1,
            "altPositions": [],
        },
        12: {
            "id": 12,
            "name": "Ana-Def",
            "position": 2,
            "price": 1,
            "altPositions": [],
        },
        21: {
            "id": 21,
            "name": "Beto-Gk1",
            "position": 1,
            "price": 1,
            "altPositions": [],
        },
        22: {
            "id": 22,
            "name": "Beto-Gk2",
            "position": 1,
            "price": 1,
            "altPositions": [],
        },
        23: {
            "id": 23,
            "name": "Beto-Fwd",
            "position": 4,
            "price": 1,
            "altPositions": [],
        },
    }
    monkeypatch.setattr(cands, "time", MagicMock())  # skip sleep

    rivals = cands.gather_rivals(
        biwenger, biwenger_players, jp_index={"by_name": {}, "by_slug": {}}
    )

    by_gk = {r["bw_id"]: r["owner_gk_count"] for r in rivals}
    assert by_gk == {11: 1, 12: 1, 21: 2, 22: 2, 23: 2}
    by_owner_id = {r["bw_id"]: r["owner_user_id"] for r in rivals}
    assert by_owner_id == {11: 1, 12: 1, 21: 2, 22: 2, 23: 2}


# --- _pick_top_per_position ---


def test_top_per_position_groups_by_primary_and_marks_multi():
    rows = [
        # 2 defs, top 1 of which is also MID-eligible
        _row(10, "Def1", pos=2, alt=[3], sf=500, clause=10_000_000),
        _row(11, "Def2", pos=2, sf=400, clause=12_000_000),
        # 1 GK
        _row(20, "Gk1", pos=1, sf=350, clause=8_000_000),
    ]
    out = recs._pick_top_per_position(rows, top=3)
    assert len(out["GK"]) == 1
    assert len(out["DEF"]) == 2
    assert len(out["MID"]) == 0  # multi-position does NOT duplicate to MID
    assert out["DEF"][0]["multi"] == ["MED"]
    assert out["DEF"][1]["multi"] == []


def test_top_per_position_caps_at_top_n():
    rows = [_row(i, f"X{i}", pos=4, sf=400 - i, clause=10_000_000) for i in range(10)]
    out = recs._pick_top_per_position(rows, top=3)
    assert len(out["FWD"]) == 3
    # sorted by SF desc
    assert out["FWD"][0]["sf"] > out["FWD"][1]["sf"] > out["FWD"][2]["sf"]


# --- _format_telegram_text ---


def test_format_telegram_text_includes_multi_badge_and_exact_euros():
    payload = {
        "budget": {
            "cash": 12_972_212,
            "max_bid": 36_334_712,
            "margin": 5_000_000,
            "margin_source": "auto",
            "target": 17_972_212,
        },
        "recommendations": {
            "GK": [],
            "DEF": [
                {
                    "bw_id": 1,
                    "name": "Vivian",
                    "owner": "Ana",
                    "clause": 12_345_678,
                    "sf": 410,
                    "multi": ["MED"],
                }
            ],
            "MID": [],
            "FWD": [],
        },
    }
    text = recs._format_telegram_text(payload)
    # Exact euros in Spanish format (dots as thousands separators).
    assert "12.972.212 €" in text
    assert "17.972.212 €" in text
    assert "36.334.712 €" in text
    assert "auto" in text  # margin_source label
    assert "Vivian (Ana)" in text
    assert "12.345.678 €" in text
    assert "SF 410" in text
    assert "multi: MED" in text


def test_format_telegram_text_marks_manual_margin():
    payload = {
        "budget": {
            "cash": 10_000_000,
            "max_bid": 30_000_000,
            "margin": 8_000_000,
            "margin_source": "manual",
            "target": 18_000_000,
        },
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    text = recs._format_telegram_text(payload)
    assert "fijo" in text


def test_format_telegram_text_dashes_when_max_bid_missing():
    payload = {
        "budget": {
            "cash": 12_972_212,
            "max_bid": 0,  # max_bid couldn't be computed (no squad data)
            "margin": 5_000_000,
            "margin_source": "auto",
            "target": 17_972_212,
        },
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    text = recs._format_telegram_text(payload)
    assert "Puja máx. Biwenger: —" in text
