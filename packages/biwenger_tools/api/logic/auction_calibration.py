"""What the daily market actually takes to win, read off the league board.

Every settled market auction is on the board — winner, winning bid and up
to three losing bids — so the auto-bid shares can be measured against the
league instead of set by feel. Pure functions; the script
`scripts/auto_bid/calibrate.py` does the reads and prints the report.
Spec: `openspec/specs/biwenger_tools/auto-bid/spec.md`.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from statistics import median

from core.constants import MADRID_TZ
from packages.biwenger_tools.api.logic.league_cash import season_entries


@dataclass(frozen=True)
class Auction:
    """One settled market auction. `price` is filled in once the player's
    price history has been read (`with_price`)."""

    player_id: int
    closed: int
    winner_id: int
    winner_name: str
    winning_bid: int
    runner_up: int | None
    my_bid: int | None
    won_by_me: bool
    price: int | None = None

    def with_price(self, price: int | None) -> "Auction":
        return replace(self, price=price)


def auctions(entries: list[dict], my_id: int) -> list[Auction]:
    """This season's market auctions from board `entries`, oldest first."""
    out = []
    for entry in season_entries(entries):
        if entry.get("type") != "market":
            continue
        for move in entry.get("content") or []:
            winner = move.get("to") or {}
            if not isinstance(winner, dict) or winner.get("id") is None:
                continue
            bids = move.get("bids") or []
            mine = [
                b["amount"] for b in bids if (b.get("user") or {}).get("id") == my_id
            ]
            won = winner["id"] == my_id
            out.append(
                Auction(
                    player_id=move["player"],
                    closed=entry["date"],
                    winner_id=winner["id"],
                    winner_name=winner.get("name") or str(winner["id"]),
                    winning_bid=int(move.get("amount") or 0),
                    runner_up=max((b["amount"] for b in bids), default=None),
                    my_bid=int(move["amount"]) if won else (mine[0] if mine else None),
                    won_by_me=won,
                )
            )
    return out


def price_on(history: dict[int, int], closed: int) -> int | None:
    """The asking price the day before `closed` — the auction resolves in the
    morning, on the price the market showed while it was open. `history` is
    Biwenger's `prices` as `{YYMMDD: price}`."""
    day_before = datetime.fromtimestamp(closed, MADRID_TZ) - timedelta(days=1)
    key = int(day_before.strftime("%y%m%d"))
    earlier = [d for d in history if d <= key]
    return history[max(earlier)] if earlier else None


def _beats(auction: Auction, percent: int) -> bool:
    """Whether a bid of price + `percent` % would have topped the winner.
    Integer maths, so a boundary never moves on float rounding."""
    return auction.price * (100 + percent) > auction.winning_bid * 100


def win_rate(rows: list[Auction], share: float) -> float:
    """Share of priced `rows` a bid of price × (1 + `share`) would have won."""
    priced = [r for r in rows if r.price]
    if not priced:
        return 0.0
    percent = round(share * 100)
    return sum(_beats(r, percent) for r in priced) / len(priced)


def share_to_win(rows: list[Auction], target: float) -> float | None:
    """The smallest whole-percent share that wins at least `target` of `rows`,
    up to +100 %; `None` if even that is not enough or there is no data."""
    if not any(r.price for r in rows):
        return None
    for percent in range(0, 101):
        if win_rate(rows, percent / 100) >= target:
            return percent / 100
    return None


def left_on_the_table(rows: list[Auction]) -> int:
    """What we paid, in auctions we won, above the next best bid — or above
    the asking price when nobody else bid."""
    return sum(
        r.winning_bid - max(r.runner_up or 0, r.price or 0) for r in rows if r.won_by_me
    )


def overbid_by_winner(
    rows: list[Auction], min_price: int
) -> dict[str, tuple[int, float]]:
    """`{manager: (auctions won, median share over price)}` for priced
    auctions at or above `min_price`."""
    shares: dict[str, list[float]] = {}
    for r in rows:
        if r.price and r.price >= min_price:
            shares.setdefault(r.winner_name, []).append(r.winning_bid / r.price - 1)
    return {
        name: (len(values), round(median(values), 4)) for name, values in shares.items()
    }
