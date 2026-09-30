"""Every manager's cash and maximum bid, rebuilt from the league board.

The league hides balances, so nothing returns a rival's cash. Every movement
of money is on the board, though, and the starting balance is known — so cash
is the starting balance plus the signed sum of the season's movements.

Pure functions only: `actions.run_league_cash` does the reads and the sending.
Spec: `openspec/specs/biwenger_tools/league-cash/spec.md`.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from html import escape

from core.constants import MADRID_TZ
from core.sdk.biwenger import board_entry_key
from packages.biwenger_tools.api.player_formatting import short_position, shown_score

SEASON_START_TYPE = "seasonStarted"

# Entry types that move money between a `from` and a `to`.
_TRANSFER_TYPES = frozenset({"transfer", "market", "adminTransfer"})

# `transfer` kinds seen so far: a plain sale or purchase, and a clause. Any
# other kind — an exchange is the likely one — is booked the same way but
# reported, since that is a guess.
_SEEN_TRANSFER_KINDS = frozenset({None, "clause"})


@dataclass(frozen=True)
class CashBook:
    """Rebuilt cash per manager id, plus any money-carrying type it could not read."""

    cash: dict[int, int]
    unknown_types: frozenset[str]
    starting_balance: int = 0

    def cash_of(self, manager_id: int) -> int:
        """A manager with no movement this season is still at the start."""
        return self.cash.get(manager_id, self.starting_balance)


def _user_id(user) -> int | None:
    return int(user["id"]) if isinstance(user, dict) and user.get("id") else None


def season_entries(entries: list[dict]) -> list[dict]:
    """The entries dated at or after the latest season start, oldest first.

    Raises `ValueError` when the read never reached a season start: the
    rebuild would be missing the season's first movements.
    """
    starts = [e["date"] for e in entries if e.get("type") == SEASON_START_TYPE]
    if not starts:
        raise ValueError(
            f"The board read holds no {SEASON_START_TYPE} entry; "
            "it does not reach back to the start of the season."
        )
    season_start = max(starts)
    return sorted(
        (e for e in entries if e.get("date", 0) >= season_start),
        key=lambda e: e["date"],
    )


def with_archive(live: list[dict], archived: list[dict]) -> tuple[list[dict], int]:
    """The live read plus the archived entries it no longer returns, and how many
    of those the rebuild uses (dated at or after the union's season start).

    Deduped by `board_entry_key`; any order, since `season_entries` sorts.
    """
    live_keys = {board_entry_key(e) for e in live}
    lost = [e for e in archived if board_entry_key(e) not in live_keys]
    entries = live + lost
    starts = [e["date"] for e in entries if e.get("type") == SEASON_START_TYPE]
    since = max(starts, default=0)
    return entries, sum(1 for e in lost if e.get("date", 0) >= since)


def rebuild(entries: list[dict], starting_balance: int) -> CashBook:
    """Cash per manager from board `entries` (any order, any history depth)."""
    moves: dict[int, int] = {}
    rounds: dict[int, dict] = {}
    unknown: set[str] = set()

    def add(user, amount) -> None:
        uid = _user_id(user)
        if uid is not None:
            moves[uid] = moves.get(uid, 0) + int(amount or 0)

    for entry in season_entries(entries):
        kind, content = entry.get("type"), entry.get("content")
        if kind in _TRANSFER_TYPES:
            for move in content or []:
                add(move.get("to"), -(move.get("amount") or 0))
                add(move.get("from"), move.get("amount"))
                if kind == "transfer" and move.get("type") not in _SEEN_TRANSFER_KINDS:
                    unknown.add(f"transfer:{move.get('type')}")
        elif kind == "clauseIncrement":
            # A negative amount is the 75 % refund of a lowered clause.
            for move in content or []:
                add(move.get("user"), -(move.get("amount") or 0))
        elif kind == "bonus":
            for move in content or []:
                add(move.get("user"), move.get("amount"))
        elif kind == "roundFinished":
            # A score correction republishes the whole round; the latest wins.
            rounds[content["round"]["id"]] = content
        elif '"amount"' in json.dumps(content):
            # No other type has ever carried money; the first one that does
            # is named rather than guessed at.
            unknown.add(kind)

    for content in rounds.values():
        for result in content.get("results") or []:
            add(result.get("user"), result.get("bonus"))

    cash = {uid: starting_balance + delta for uid, delta in moves.items()}
    return CashBook(cash, frozenset(unknown), starting_balance)


def squad_value(squad: list[dict], players: dict) -> int:
    """Sum of today's catalogue prices over a squad; unknown players count 0."""
    return sum(int((players.get(p.get("id")) or {}).get("price") or 0) for p in squad)


def max_bid(cash: int, squad_value: int) -> int:
    """`maximumBid = quarterTeam`: cash plus a quarter of the squad's value."""
    return cash + squad_value // 4


def _eur(amount: int) -> str:
    return f"{amount:,} €".replace(",", ".")


def notes(
    unknown_types: frozenset[str],
    rebuilt_mine: int,
    real_mine: int,
    lost: int | None = 0,
) -> list[str]:
    """The lines that say how far the figures can be trusted, in Spanish.

    `lost` is how many archived entries the live board no longer returns;
    None when the archive could not be read.
    """
    lines = []
    if rebuilt_mine == real_mine:
        lines.append("✅ Tu saldo reconstruido cuadra con Biwenger.")
    else:
        lines.append(
            f"⚠️ Tu saldo reconstruido ({_eur(rebuilt_mine)}) no cuadra "
            f"con el real ({_eur(real_mine)})."
        )
    if unknown_types:
        lines.append(
            f"⚠️ Movimientos desconocidos ({', '.join(sorted(unknown_types))}): "
            "las cifras pueden estar mal."
        )
    if lost is None:
        lines.append(
            "⚠️ No se pudo leer el archivo del tablón: solo cuenta lo que "
            "Biwenger devuelve hoy."
        )
    elif lost:
        lines.append(
            f"⚠️ Biwenger ya no devuelve {lost} "
            f"movimiento{'s' if lost != 1 else ''} de la temporada; "
            "salen del archivo."
        )
    lines.append("Puja máx. = saldo + ¼ de la plantilla, sin restar pujas pendientes.")
    return lines


def ranked(rows: list[dict]) -> list[dict]:
    """Rows ordered by maximum bid, highest first."""
    return sorted(rows, key=lambda r: r["max_bid"], reverse=True)


@dataclass(frozen=True)
class Reach:
    """Who can pay a clause: from cash alone, or only by going negative."""

    by_cash: tuple[dict, ...] = ()
    by_max_bid: tuple[dict, ...] = ()

    @property
    def anyone(self) -> bool:
        return bool(self.by_cash or self.by_max_bid)


def reach(clause: int, rivals: list[dict]) -> Reach:
    """Split `rivals` (`name`, `cash`, `max_bid`) by how they could pay `clause`.

    Paying past cash leaves the rival negative, which costs them the round if
    it is still negative when the matchday starts — a real but lesser threat.
    """
    if not clause:
        return Reach()
    by_cash = tuple(r for r in rivals if r["cash"] >= clause)
    by_max_bid = tuple(r for r in rivals if r["cash"] < clause <= r["max_bid"])
    return Reach(by_cash, by_max_bid)


def protection_ending(rows: list[dict], now: float, within: float) -> list[dict]:
    """Squad rows whose clause lock ends in `(now, now + within]`."""
    return [
        r
        for r in rows
        if r.get("clause_locked_until") is not None
        and now < r["clause_locked_until"] <= now + within
    ]


def exposed(rows: list[dict], n: int) -> list[dict]:
    """The `n` rows with the best shown projection; unprojected rows last out."""
    scored = [r for r in rows if shown_score(r) is not None]
    return sorted(scored, key=shown_score, reverse=True)[:n]


def _names(rivals: tuple[dict, ...]) -> str:
    return ", ".join(
        escape(r["name"]) + (" (pacto)" if r.get("pacted") else "") for r in rivals
    )


def protection_alert(rows: list[dict], rivals: list[dict]) -> str | None:
    """Telegram HTML for players whose protection is ending, or `None` when no
    rival could pay any of their clauses — then there is nothing to act on."""
    blocks = []
    for row in rows:
        who = reach(row.get("clause_value") or 0, rivals)
        if not who.anyone:
            continue
        opens = datetime.fromtimestamp(row["clause_locked_until"], MADRID_TZ)
        lines = [
            f"<b>{escape(row['name'])}</b> ({short_position(row.get('position_id'))})"
            f" · cláusula {_eur(row['clause_value'])}",
            f"   Clausulable desde el {opens.strftime('%d/%m a las %H:%M')}",
        ]
        if who.by_cash:
            lines.append(f"   🔴 Con su saldo: {_names(who.by_cash)}")
        if who.by_max_bid:
            lines.append(f"   🟠 Quedándose en negativo: {_names(who.by_max_bid)}")
        blocks.append("\n".join(lines))
    if not blocks:
        return None
    return (
        "🔓 <b>Se acaba la protección</b>\n\n"
        + "\n\n".join(blocks)
        + "\n\n<i>Si te interesa, sube la cláusula en la app.</i>"
    )


def exposure_rows(rows: list[dict], rivals: list[dict]) -> list[dict]:
    """For each squad row: its shown projection, market value, clause, how many rivals
    reach it from cash and how many only by going negative, and its lock
    (`None` when open)."""
    out = []
    for row in rows:
        clause = row.get("clause_value") or 0
        who = reach(clause, rivals)
        out.append(
            {
                "name": row["name"],
                "projection": shown_score(row),
                "value": int(row.get("price") or 0),
                "clause": clause,
                "by_cash": len(who.by_cash),
                "by_max_bid": len(who.by_max_bid),
                "locked_until": row.get("clause_locked_until"),
            }
        )
    return out
