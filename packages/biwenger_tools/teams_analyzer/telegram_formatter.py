"""Formatea los mensajes que se envían a Telegram (texto y CSV)."""

import csv
import io
import re
from html import escape

from core.sdk.jp import get_predict_rate

POSITION_SHORT = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}

# Tipos en JP.predict
SCORE_AS = 1
SCORE_SF = 2
SCORE_AVG = 16

TELEGRAM_LIMIT = 4096


def _short_pos(pos_id) -> str:
    return POSITION_SHORT.get(pos_id, "?")


def _price_millions(price) -> str:
    if not price:
        return "0M"
    return f"{round(int(price) / 1_000_000)}M"


def _price_increment(inc) -> str:
    if inc is None:
        return ""
    inc = int(inc)
    if inc == 0:
        return "·"
    arrow = "⬆️" if inc > 0 else "⬇️"
    abs_k = abs(inc) // 1000
    if abs_k >= 1000:
        return f" · {arrow}{abs_k / 1000:.1f}M"
    return f" · {arrow}{abs_k}K"


def _status_emoji(jp_player: dict | None) -> str:
    """Emoji semáforo por jugador.

    🔴 lesionado / sancionado / no juega / sin partido / SF < 100
    🟡 100 ≤ SF < 300
    🟢 SF ≥ 300
    ⚪ sin datos JP (no encontrado)
    """
    if jp_player is None:
        return "⚪"
    if jp_player.get("status") in ("injured", "suspended"):
        return "🔴"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "🔴"
    if next_match.get("playerInLineup") is False:
        return "🔴"
    sf = get_predict_rate(jp_player, SCORE_SF)
    if sf is None:
        return "🔴"
    if sf >= 300:
        return "🟢"
    if sf >= 100:
        return "🟡"
    return "🔴"


def _juega_line(jp_player: dict | None) -> str:
    if jp_player is None:
        return "  Sin datos JP"
    status = jp_player.get("status", "ok")
    status_info = (jp_player.get("statusInfo") or "").strip()
    if status == "injured":
        extra = f" ({escape(status_info)})" if status_info else ""
        return f"  Juega: ❌ lesionado{extra}"
    if status == "suspended":
        return "  Juega: ❌ sancionado"
    if status == "doubt":
        extra = f" ({escape(status_info)})" if status_info else ""
        return f"  Juega: ❓ duda{extra}"

    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "  Juega: ⏸️ sin partido"

    in_lineup = next_match.get("playerInLineup")
    is_local = next_match.get("isLocal")
    venue = "casa" if is_local else "fuera"
    icon = "✅" if in_lineup else "❓"
    return f"  Juega: {icon} {venue}"


def format_player_row(
    name: str,
    position_id,
    price,
    jp_player: dict | None,
) -> str:
    emoji = _status_emoji(jp_player)
    pos = _short_pos(position_id)
    price_str = _price_millions(price)
    inc_str = _price_increment(jp_player.get("priceIncrement")) if jp_player else ""

    header = f"{emoji} {escape(name)} ({pos}) · {price_str}{inc_str}"

    if jp_player is None:
        return header

    sf = get_predict_rate(jp_player, SCORE_SF)
    as_ = get_predict_rate(jp_player, SCORE_AS)
    avg = get_predict_rate(jp_player, SCORE_AVG)
    streak = jp_player.get("streak", 0)

    def fmt(v):
        return str(v) if v is not None else "-"

    stats = f"  SF:{fmt(sf)} | AS:{fmt(as_)} | Avg:{fmt(avg)} | Racha:{streak}"
    juega = _juega_line(jp_player)
    return f"{header}\n{stats}\n{juega}"


def _sort_key_sf_desc(row: dict):
    """Ordena: tiene SF (con valor) > sin SF; dentro, SF desc."""
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    return (0 if sf is None else 1, sf or 0)


def build_my_team_message(rows: list[dict]) -> str:
    """rows: [{name, position_id, price, jp_player}]."""
    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)
    body = "\n\n".join(
        format_player_row(r["name"], r["position_id"], r["price"], r["jp_player"])
        for r in sorted_rows
    )
    return f"<b>🛡️ MI EQUIPO</b> ({len(sorted_rows)})\n\n{body}"


def build_market_message(rows: list[dict], top_n: int = 10) -> str:
    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)[:top_n]
    body = "\n\n".join(
        format_player_row(r["name"], r["position_id"], r["price"], r["jp_player"])
        for r in sorted_rows
    )
    return f"<b>🛒 MERCADO</b> (top {len(sorted_rows)} por SF)\n\n{body}"


def build_rival_messages(rivals: dict[str, list[dict]]) -> list[str]:
    """rivals: {manager_name: [row, ...]}.

    Devuelve una lista de mensajes — uno por rival, partidos si exceden el
    límite de Telegram.
    """
    messages: list[str] = []
    for manager_name, rows in rivals.items():
        sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)
        header = f"<b>👤 {escape(manager_name)}</b> ({len(sorted_rows)})\n\n"
        body_parts = [
            format_player_row(r["name"], r["position_id"], r["price"], r["jp_player"])
            for r in sorted_rows
        ]
        chunk = header
        for part in body_parts:
            piece = part + "\n\n"
            if len(chunk) + len(piece) > TELEGRAM_LIMIT:
                messages.append(chunk.rstrip())
                chunk = header + piece
            else:
                chunk += piece
        if chunk.strip():
            messages.append(chunk.rstrip())
    return messages


def build_all_messages(
    my_team: list[dict],
    market: list[dict],
    rivals: dict[str, list[dict]],
    market_top_n: int = 10,
) -> list[str]:
    """Construye todos los mensajes en orden (mi equipo, mercado, rivales)."""
    messages = [
        build_my_team_message(my_team),
        build_market_message(market, market_top_n),
    ]
    messages.extend(build_rival_messages(rivals))
    return messages


_CSV_COLUMNS = [
    "Nombre",
    "Pos",
    "Precio",
    "SF",
    "AS",
    "Avg",
    "Racha",
    "Juega",
    "Estado",
    "Variacion",
]


def _variacion_str(inc) -> str:
    if inc is None or inc == 0:
        return "0"
    sign = "+" if inc > 0 else "-"
    abs_val = abs(inc)
    if abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:.1f}M"
    return f"{sign}{abs_val // 1_000}K"


def _juega_str(jp_player: dict | None) -> str:
    if jp_player is None:
        return "sin datos"
    status = jp_player.get("status", "ok")
    if status == "injured":
        return "lesionado"
    if status == "suspended":
        return "sancionado"
    if status == "doubt":
        return "duda"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "sin partido"
    if next_match.get("playerInLineup") is False:
        return "no convocado"
    venue = "casa" if next_match.get("isLocal") else "fuera"
    return venue


def _csv_player_row(row: dict) -> dict:
    jp = row.get("jp_player")
    name = row.get("name", "")
    pos = _short_pos(row.get("position_id"))
    price = _price_millions(row.get("price", 0))

    if jp is None:
        return dict(
            zip(
                _CSV_COLUMNS,
                [name, pos, price, "-", "-", "-", "-", "sin datos", "desconocido", "0"],
            )
        )

    def fmt(v):
        return str(v) if v is not None else "-"

    sf = get_predict_rate(jp, SCORE_SF)
    as_ = get_predict_rate(jp, SCORE_AS)
    avg = get_predict_rate(jp, SCORE_AVG)

    return {
        "Nombre": name,
        "Pos": pos,
        "Precio": price,
        "SF": fmt(sf),
        "AS": fmt(as_),
        "Avg": fmt(avg),
        "Racha": str(jp.get("streak", 0)),
        "Juega": _juega_str(jp),
        "Estado": jp.get("status", "ok"),
        "Variacion": _variacion_str(jp.get("priceIncrement")),
    }


def _rows_to_csv_bytes(
    rows: list[dict], extra_col: str | None = None
) -> bytes:
    buf = io.StringIO()
    cols = ([extra_col] if extra_col else []) + _CSV_COLUMNS
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in rows:
        csv_row = _csv_player_row(r)
        if extra_col:
            csv_row[extra_col] = r.get(extra_col, "")
        writer.writerow(csv_row)
    return buf.getvalue().encode("utf-8-sig")


def _count_status(rows: list[dict]) -> tuple[int, int, int, int]:
    """Returns (green, yellow, red, white) counts."""
    g = y = r = w = 0
    for row in rows:
        e = _status_emoji(row.get("jp_player"))
        if e == "🟢":
            g += 1
        elif e == "🟡":
            y += 1
        elif e == "🔴":
            r += 1
        else:
            w += 1
    return g, y, r, w


def _safe_filename(name: str) -> str:
    slug = re.sub(r"[^\w]", "_", name.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return f"{slug}.csv"


def build_team_csv(
    rows: list[dict], team_name: str = "Mi equipo"
) -> tuple[bytes, str, str]:
    """Build a CSV for one team.

    Returns (csv_bytes, caption_html, filename).
    """
    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)
    g, y, r, _ = _count_status(sorted_rows)
    caption = (
        f"🛡️ <b>{escape(team_name)}</b> — {len(sorted_rows)} jug.\n"
        f"🟢 {g} · 🟡 {y} · 🔴 {r}"
    )
    filename = (
        "mi_equipo.csv" if team_name == "Mi equipo" else _safe_filename(team_name)
    )
    return _rows_to_csv_bytes(sorted_rows), caption, filename


def build_market_csv(
    rows: list[dict], top_n: int = 10
) -> tuple[bytes, str, str]:
    """Build a CSV for the market top-N.

    Returns (csv_bytes, caption_html, filename).
    """
    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)[:top_n]
    caption = f"🛒 <b>Mercado</b> — top {len(sorted_rows)} por SF"
    return _rows_to_csv_bytes(sorted_rows), caption, "mercado.csv"


def build_all_teams_csv(
    my_team: list[dict],
    rivals: dict[str, list[dict]],
) -> list[tuple[bytes, str, str]]:
    """One CSV per team (mi equipo first, then rivals).

    Returns list of (csv_bytes, caption_html, filename).
    """
    results = []
    results.append(build_team_csv(my_team, "Mi equipo"))
    for manager_name, rows in rivals.items():
        results.append(build_team_csv(rows, manager_name))
    return results


__all__ = [
    "format_player_row",
    "build_my_team_message",
    "build_market_message",
    "build_rival_messages",
    "build_all_messages",
    "build_team_csv",
    "build_market_csv",
    "build_all_teams_csv",
]
