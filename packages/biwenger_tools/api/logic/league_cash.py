"""Every manager's cash and maximum bid, rebuilt from the league board.

The league hides balances, so nothing returns a rival's cash. Every movement
of money is on the board, though, and the starting balance is known — so cash
is the starting balance plus the signed sum of the season's movements.

Pure functions only: `actions.run_league_cash` does the reads and the sending.
Spec: `openspec/specs/biwenger_tools/league-cash/spec.md`.
"""

import json
from dataclasses import dataclass

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


def _season_entries(entries: list[dict]) -> list[dict]:
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


def rebuild(entries: list[dict], starting_balance: int) -> CashBook:
    """Cash per manager from board `entries` (any order, any history depth)."""
    moves: dict[int, int] = {}
    rounds: dict[int, dict] = {}
    unknown: set[str] = set()

    def add(user, amount) -> None:
        uid = _user_id(user)
        if uid is not None:
            moves[uid] = moves.get(uid, 0) + int(amount or 0)

    for entry in _season_entries(entries):
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
    unknown_types: frozenset[str], rebuilt_mine: int, real_mine: int
) -> list[str]:
    """The lines that say how far the figures can be trusted, in Spanish."""
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
    lines.append("Puja máx. = saldo + ¼ de la plantilla, sin restar pujas pendientes.")
    return lines


def ranked(rows: list[dict]) -> list[dict]:
    """Rows ordered by maximum bid, highest first."""
    return sorted(rows, key=lambda r: r["max_bid"], reverse=True)
