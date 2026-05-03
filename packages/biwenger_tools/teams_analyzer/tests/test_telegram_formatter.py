from packages.biwenger_tools.teams_analyzer.telegram_formatter import (
    build_all_messages,
    build_my_team_message,
    build_market_message,
    build_rival_messages,
    format_player_row,
)


def _jp(
    rate_sf=None, status="ok", in_lineup=True, is_local=True, match_status="pending"
):
    predict = []
    if rate_sf is not None:
        predict.append({"type": 2, "rate": rate_sf})
    return {
        "name": "X",
        "status": status,
        "priceIncrement": 0,
        "streak": 1,
        "predict": predict,
        "nextMatch": {
            "status": match_status,
            "playerInLineup": in_lineup,
            "isLocal": is_local,
        },
    }


def test_format_row_green_for_high_sf():
    row = format_player_row("Vini Jr", 4, 42_000_000, _jp(rate_sf=900))
    assert row.startswith("🟢 Vini Jr (DEL)")
    assert "SF:900" in row
    assert "Juega: ✅ casa" in row


def test_format_row_yellow_for_mid_sf():
    row = format_player_row("Mid", 3, 5_000_000, _jp(rate_sf=200))
    assert row.startswith("🟡")


def test_format_row_red_for_injured():
    row = format_player_row("Hurt", 2, 3_000_000, _jp(rate_sf=500, status="injured"))
    assert row.startswith("🔴")
    assert "lesionado" in row


def test_format_row_red_when_no_match():
    row = format_player_row(
        "Free", 3, 2_000_000, _jp(rate_sf=None, match_status="break")
    )
    assert row.startswith("🔴")
    assert "sin partido" in row


def test_format_row_white_when_no_jp_data():
    row = format_player_row("Unknown", 1, 1_000_000, None)
    assert row.startswith("⚪")
    assert "Unknown (POR)" in row


def test_format_row_escapes_html():
    row = format_player_row("<script>", 4, 1_000_000, None)
    assert "<script>" not in row
    assert "&lt;script&gt;" in row


def test_my_team_sorted_by_sf_desc():
    rows = [
        {"name": "Low", "position_id": 3, "price": 1, "jp_player": _jp(rate_sf=100)},
        {"name": "High", "position_id": 3, "price": 1, "jp_player": _jp(rate_sf=500)},
        {"name": "None", "position_id": 3, "price": 1, "jp_player": None},
    ]
    msg = build_my_team_message(rows)
    pos_high = msg.index("High")
    pos_low = msg.index("Low")
    pos_none = msg.index("None")
    assert pos_high < pos_low < pos_none


def test_market_caps_to_top_n():
    rows = [
        {
            "name": f"P{i}",
            "position_id": 3,
            "price": 1,
            "jp_player": _jp(rate_sf=i * 10),
        }
        for i in range(15)
    ]
    msg = build_market_message(rows, top_n=5)
    assert "top 5" in msg


def test_rivals_split_when_too_long():
    big_jp = _jp(rate_sf=400)
    rows = [
        {"name": f"Player{i}", "position_id": 3, "price": 1, "jp_player": big_jp}
        for i in range(60)
    ]
    msgs = build_rival_messages({"Big Squad": rows})
    assert len(msgs) >= 2
    for m in msgs:
        assert len(m) <= 4096


def test_build_all_messages_returns_my_team_market_then_rivals():
    msgs = build_all_messages(
        my_team=[
            {"name": "A", "position_id": 1, "price": 1, "jp_player": _jp(rate_sf=10)}
        ],
        market=[
            {"name": "B", "position_id": 1, "price": 1, "jp_player": _jp(rate_sf=10)}
        ],
        rivals={
            "R": [
                {
                    "name": "C",
                    "position_id": 1,
                    "price": 1,
                    "jp_player": _jp(rate_sf=10),
                }
            ]
        },
    )
    assert len(msgs) == 3
    assert "MI EQUIPO" in msgs[0]
    assert "MERCADO" in msgs[1]
    assert "R" in msgs[2]
