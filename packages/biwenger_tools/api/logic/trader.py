"""Which players to sell and to buy on price streaks. Pure: no I/O.

Sell the squad's fallers and the bench that will not do much, buy the
market's risers, and let the one pay for the other, inside the owner's limits:
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
    min_squad: int
    # A bench player projected below this is sold whatever his price does.
    dead_sf: int


@dataclass(frozen=True)
class Move:
    row: dict
    amount: int
    streak: int
    reason: str = ""


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
    waiting: list[Move] = field(default_factory=list)


def round_eve(rounds: list[dict] | None, now: float) -> bool:
    """Whether a round's first match still to be played falls today or
    tomorrow, Madrid time.

    Only rounds still `pending` start; the games left in one already under way
    do not. A postponed round stays `pending` with most of its games played,
    so only games not yet played count. An unreadable calendar answers True,
    the careful side.
    """
    starts = [
        g["date"]
        for r in rounds or []
        if r.get("status") == "pending"
        for g in r.get("games") or []
        if g.get("date") and g["date"] > now and g.get("status") != "finished"
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


def plan_sells(
    squad: list[dict], history: list[dict[int, int]], rules: Rules
) -> tuple[list[Move], list[tuple[dict, str]], list[dict]]:
    """`(sells, held, keep)`: the players to sell at today's price — the
    fallers, and the bench projected below `dead_sf` whatever his price —
    weakest projection first, and why the others stay. Never a starter of the
    best eleven, never below `min_squad` — an eleven and a bench — and never
    one whose sale leaves no eleven that plays."""
    fallers = sorted(
        (
            (row, s)
            for row in squad
            if (s := streak(history, row["bw_id"])) <= -rules.sell_after_falls
            or lineup.projected_sf(row) < rules.dead_sf
        ),
        key=lambda rs: (lineup.projected_sf(rs[0]), rs[1]),
    )
    starters = best_eleven_ids(squad)
    keep = list(squad)
    sells: list[Move] = []
    held: list[tuple[dict, str]] = []
    for row, s in fallers:
        if row["bw_id"] in starters:
            held.append((row, "titular del mejor once"))
            continue
        if len(keep) - 1 < rules.min_squad:
            held.append((row, "plantilla mínima"))
            continue
        rest = [r for r in keep if r["bw_id"] != row["bw_id"]]
        if not has_eleven(rest):
            held.append((row, "sin él no queda un once que juegue"))
            continue
        keep = rest
        why = (
            ""
            if s <= -rules.sell_after_falls
            else f"proyección baja (SF {lineup.projected_sf(row)})"
        )
        sells.append(Move(row, int(row.get("price") or 0), s, why))
    return sells, held, keep


def plan_buys(
    keep: list[dict],
    market: list[dict],
    history: list[dict[int, int]],
    *,
    wallet: int,
    floor: int,
    rules: Rules,
    already_bid: frozenset | set = frozenset(),
) -> tuple[list[Move], list[tuple[dict, str]], int]:
    """`(buys, skipped, wallet_after)`: the risers to bid on, best projection
    first, while the wallet stays at or above `floor`. A player with a bid
    already waiting is left alone."""
    owned = {r["bw_id"] for r in keep}
    risers = sorted(
        (
            (row, s)
            for row in market
            if row["bw_id"] not in owned
            and row["bw_id"] not in already_bid
            and (s := streak(history, row["bw_id"])) >= rules.buy_after_rises
            and lineup.projected_sf(row) >= rules.buy_min_sf
        ),
        key=lambda rs: (-lineup.projected_sf(rs[0]), -rs[1]),
    )
    buys: list[Move] = []
    skipped: list[tuple[dict, str]] = []
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
    return buys, skipped, wallet


def plan(
    squad: list[dict],
    market: list[dict],
    history: list[dict[int, int]],
    *,
    cash: int,
    round_eve: bool,
    negative_limit: int,
    rules: Rules,
    committed: int = 0,
    already_bid: frozenset | set = frozenset(),
) -> Plan:
    """The day's sells and bids, the sells assumed sold at today's price. Bids
    already waiting (`committed`) are spent; `floor` is the lowest the wallet
    may end at."""
    sells, held, keep = plan_sells(squad, history, rules)
    floor = 0 if round_eve else -negative_limit
    buys, skipped, wallet = plan_buys(
        keep,
        market,
        history,
        wallet=cash + sum(m.amount for m in sells) - committed,
        floor=floor,
        rules=rules,
        already_bid=already_bid,
    )
    return Plan(sells, buys, cash, wallet, floor, round_eve, held, skipped)


def sale_offers(
    sells: list[Move], inbox: list[dict], min_share: float
) -> list[tuple[Move, dict]]:
    """For each planned sell, the best received offer for him alone worth at
    least `min_share` of his price. Offers for anyone else, or for him with
    others, are never returned."""
    taken = []
    for move in sells:
        pid = move.row["bw_id"]
        offers = [
            o
            for o in inbox
            if (o.get("requestedPlayers") or []) == [pid]
            and (o.get("amount") or 0) >= move.amount * min_share
        ]
        if offers:
            taken.append((move, max(offers, key=lambda o: o["amount"])))
    return taken


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
    lines.append(
        f"<b>{verb_sell}</b>"
        if result.sells or result.waiting
        else f"{verb_sell}: nadie"
    )
    for m in result.sells:
        why = m.reason or f"{-m.streak} días bajando"
        lines.append(f"• {escape(m.row['name'])} — {_eur(m.amount)}, {why}")
    for m in result.waiting:
        lines.append(
            f"• <i>{escape(m.row['name'])}: a la venta, sin oferta aceptable aún</i>"
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
