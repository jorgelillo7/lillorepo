"""Which players to sell and to buy on price streaks. Pure: no I/O.

Sell the squad's fallers, buy the market's risers, inside the owner's limits:
the starters of the best eleven are never sold — good players are kept for
their points and only the rest rotates on price — the squad must still field
an eleven that plays, and on the eve of a
round the wallet may not end below zero. Away from a round it may go negative
down to a limit, because the whole squad is on sale every day and something
sells by the next morning.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape

from core.constants import MADRID_TZ
from packages.biwenger_tools.api.logic import lineup
from packages.biwenger_tools.api.logic.price_history import streak


@dataclass(frozen=True)
class Rules:
    sell_after_falls: int
    buy_after_rises: int
    buy_margin: float
    buy_min_sf: int
    max_squad: int


@dataclass(frozen=True)
class Move:
    row: dict
    amount: int
    streak: int


@dataclass(frozen=True)
class Plan:
    sells: list[Move]
    buys: list[Move]
    cash: int
    cash_after: int
    floor: int
    round_eve: bool
    held: list[tuple[dict, str]] = field(default_factory=list)
    skipped: list[tuple[dict, str]] = field(default_factory=list)


def round_eve(rounds: list[dict] | None, now: float) -> bool:
    """Whether a round's first match falls today or tomorrow, Madrid time.

    Only rounds still `pending` start; the games left in one already under way
    do not. An unreadable calendar answers True, the careful side.
    """
    starts = [
        min(g["date"] for g in r.get("games") or [] if g.get("date"))
        for r in rounds or []
        if r.get("status") == "pending"
        and any(g.get("date") for g in r.get("games") or [])
    ]
    if not starts:
        return True
    today = datetime.fromtimestamp(now, MADRID_TZ).date()
    first = datetime.fromtimestamp(min(starts), MADRID_TZ).date()
    return first <= today + timedelta(days=1)


def best_eleven_ids(rows: list[dict]) -> set:
    """The ids the lineup search would start today. Works on copies."""
    result = lineup.solve_lineup([dict(r) for r in rows])
    return {row["bw_id"] for row, _ in (result or {}).get("starters") or [] if row}


def has_eleven(rows: list[dict]) -> bool:
    """Whether `rows` field a full eleven of players the projection expects to play.

    Works on copies: the lineup search marks the rows it is given.
    """
    result = lineup.solve_lineup([dict(r) for r in rows])
    starters = (result or {}).get("starters") or []
    return len(starters) == 11 and all(
        row is not None and lineup.plays(row) for row, _ in starters
    )


def plan(
    squad: list[dict],
    market: list[dict],
    history: list[dict[int, int]],
    *,
    cash: int,
    round_eve: bool,
    negative_limit: int,
    rules: Rules,
) -> Plan:
    """The day's sells and bids. Sales are valued at today's price and count
    towards today's bids; `floor` is the lowest the wallet may end at."""
    held: list[tuple[dict, str]] = []
    skipped: list[tuple[dict, str]] = []

    fallers = sorted(
        (
            (row, s)
            for row in squad
            if (s := streak(history, row["bw_id"])) <= -rules.sell_after_falls
        ),
        key=lambda rs: (rs[1], -(rs[0].get("price") or 0)),
    )
    starters = best_eleven_ids(squad)
    keep = list(squad)
    sells: list[Move] = []
    for row, s in fallers:
        if row["bw_id"] in starters:
            held.append((row, "titular del mejor once"))
            continue
        rest = [r for r in keep if r["bw_id"] != row["bw_id"]]
        if not has_eleven(rest):
            held.append((row, "sin él no queda un once que juegue"))
            continue
        keep = rest
        sells.append(Move(row, int(row.get("price") or 0), s))

    floor = 0 if round_eve else -negative_limit
    wallet = cash + sum(m.amount for m in sells)
    owned = {r["bw_id"] for r in keep}
    risers = sorted(
        (
            (row, s)
            for row in market
            if row["bw_id"] not in owned
            and (s := streak(history, row["bw_id"])) >= rules.buy_after_rises
            and lineup.projected_sf(row) >= rules.buy_min_sf
        ),
        key=lambda rs: (-lineup.projected_sf(rs[0]), -rs[1]),
    )
    buys: list[Move] = []
    for row, s in risers:
        if len(keep) + len(buys) >= rules.max_squad:
            skipped.append((row, "plantilla llena"))
            continue
        bid = round(int(row.get("price") or 0) * (1 + rules.buy_margin))
        if wallet - bid < floor:
            skipped.append((row, "no cabe en el saldo"))
            continue
        wallet -= bid
        buys.append(Move(row, bid, s))

    return Plan(sells, buys, cash, wallet, floor, round_eve, held, skipped)


def _eur(amount: int) -> str:
    return f"{amount / 1e6:.2f} M".replace(".", ",")


def report(result: Plan, live: bool) -> str:
    """The Telegram summary, in Spanish, HTML-escaped."""
    title = "🤖 <b>Mercado automático</b>" + (
        "" if live else " — <i>simulación, no se ha tocado nada</i>"
    )
    verb_sell, verb_buy = ("Vendo", "Pujo") if live else ("Vendería", "Pujaría")
    lines = [title, ""]
    if result.round_eve:
        lines.append("⚠️ Víspera de jornada: el saldo no puede quedar en negativo.")
    lines.append(f"Saldo {_eur(result.cash)} → {_eur(result.cash_after)}")
    lines.append("")
    lines.append(f"<b>{verb_sell}</b>" if result.sells else f"{verb_sell}: nadie")
    for m in result.sells:
        days = -m.streak
        lines.append(
            f"• {escape(m.row['name'])} — {_eur(m.amount)}, {days} días bajando"
        )
    for row, why in result.held:
        lines.append(f"• <i>se queda {escape(row['name'])}: {why}</i>")
    lines.append("")
    lines.append(f"<b>{verb_buy}</b>" if result.buys else f"{verb_buy}: por nadie")
    for m in result.buys:
        lines.append(
            f"• {escape(m.row['name'])} — {_eur(m.amount)}, {m.streak} días subiendo"
        )
    for row, why in result.skipped:
        lines.append(f"• <i>{escape(row['name'])}: {why}</i>")
    return "\n".join(lines)
