import csv
import io

from packages.biwenger_tools.teams_analyzer.telegram_formatter import (
    build_all_messages,
    build_all_teams_csv,
    build_market_csv,
    build_market_message,
    build_my_team_message,
    build_rival_messages,
    build_team_csv,
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


def test_format_row_price_increment_under_1m():
    """Increments below 1M render as Kxxx with no decimal."""
    jp = _jp(rate_sf=400)
    jp["priceIncrement"] = 380_000
    row = format_player_row("X", 4, 10_000_000, jp)
    assert "⬆️380K" in row


def test_format_row_price_increment_negative_million():
    """Negative drops over 1M render with one decimal as M, with the down arrow."""
    jp = _jp(rate_sf=400)
    jp["priceIncrement"] = -2_500_000
    row = format_player_row("X", 4, 10_000_000, jp)
    assert "⬇️2.5M" in row


def test_format_row_price_increment_zero():
    """Increment of 0 renders as a neutral middle dot, no arrow."""
    jp = _jp(rate_sf=400)
    jp["priceIncrement"] = 0
    row = format_player_row("X", 4, 10_000_000, jp)
    assert "⬆️" not in row and "⬇️" not in row


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


# --- CSV builders ---


def _row(name="Test", pos=3, price=5_000_000, rate_sf=300):
    return {
        "name": name,
        "position_id": pos,
        "price": price,
        "jp_player": _jp(rate_sf=rate_sf),
    }


def _parse_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_build_team_csv_returns_bytes_and_caption_and_filename():
    rows = [_row("Vini Jr")]
    data, caption, filename = build_team_csv(rows, "Mi equipo")
    assert isinstance(data, bytes)
    assert "Mi equipo" in caption
    assert filename == "mi_equipo.csv"


def test_build_team_csv_caption_contains_status_counts():
    rows = [_row(rate_sf=400), _row(rate_sf=150), _row(rate_sf=50)]
    _, caption, _ = build_team_csv(rows, "Mi equipo")
    assert "🟢" in caption and "🟡" in caption and "🔴" in caption


def test_build_team_csv_rival_filename_slugified():
    rows = [_row()]
    _, _, filename = build_team_csv(rows, "Manager Pérez")
    assert filename.endswith(".csv")
    assert " " not in filename


def test_build_team_csv_contains_player_data():
    rows = [_row("Bellingham", pos=3, price=20_000_000, rate_sf=400)]
    data, _, _ = build_team_csv(rows)
    parsed = _parse_csv(data)
    assert len(parsed) == 1
    assert parsed[0]["Nombre"] == "Bellingham"
    assert parsed[0]["Pos"] == "MED"
    assert parsed[0]["Precio"] == "20M"
    assert parsed[0]["SF"] == "400"


def test_build_market_csv_caps_rows():
    rows = [_row(f"P{i}", rate_sf=i * 10) for i in range(20)]
    data, caption, filename = build_market_csv(rows, top_n=5)
    parsed = _parse_csv(data)
    assert len(parsed) == 5
    assert "top 5" in caption
    assert filename == "mercado.csv"


def test_build_market_csv_sorted_by_sf_desc():
    rows = [_row("Low", rate_sf=100), _row("High", rate_sf=500)]
    data, _, _ = build_market_csv(rows, top_n=10)
    parsed = _parse_csv(data)
    assert parsed[0]["Nombre"] == "High"
    assert parsed[1]["Nombre"] == "Low"


def test_build_all_teams_csv_order_and_count():
    my_team = [_row("Me")]
    rivals = {"Rival A": [_row("A1")], "Rival B": [_row("B1")]}
    results = build_all_teams_csv(my_team, rivals)
    assert len(results) == 3
    _, first_caption, _ = results[0]
    assert "Mi equipo" in first_caption


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
