"""Measure what the daily market takes to win, against the auto-bid shares.

    PYTHONPATH=. python3 packages/biwenger_tools/scripts/auto_bid/calibrate.py

Read-only: it reads the league board and each auctioned player's public
price history, and prints. Nothing is written anywhere, so there is no
`--apply`. Biwenger credentials from `packages/biwenger_tools/api/.env`.

The report answers one question — are `TIER_T*_OVERBID` in `auto_bid.py`
still right? — and leaves the answer to a person: the market is split by
price, the tiers by projection, and which band a tier's players live in is a
judgement, not a lookup. How to read it is in the auto-bid spec.

Price histories come from `cf.biwenger.com/players/la-liga/{slug}`, the
rate-limited endpoint (parallel reads 429; the budget is shared with the
phone app). They are read one at a time with a delay and cached per player
per day under `.cache/`, so a second run the same day costs no requests.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from core.sdk.biwenger import BIWENGER_CF_BASE, BiwengerClient  # noqa: E402
from packages.biwenger_tools.api import config  # noqa: E402
from packages.biwenger_tools.api.logic import auction_calibration as ac  # noqa: E402
from packages.biwenger_tools.api.logic import auto_bid  # noqa: E402
from packages.biwenger_tools.api.logic.league_cash import (  # noqa: E402
    SEASON_START_TYPE,
)
from packages.biwenger_tools.api.logic.orchestration import (  # noqa: E402
    build_biwenger_session,
)

PRICES_URL = BIWENGER_CF_BASE + "/players/la-liga/{slug}"
CACHE = Path(__file__).parent / ".cache"
BANDS = (
    (0, 2_000_000, "< 2M"),
    (2_000_000, 5_000_000, "2–5M"),
    (5_000_000, 10_000_000, "5–10M"),
    (10_000_000, 10**12, "≥ 10M"),
)
SHARES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
TARGETS = (0.7, 0.8, 0.9)


def _eur(n: int | None) -> str:
    return "—" if n is None else f"{n:,} €".replace(",", ".")


def _prices(slug: str, delay: float) -> dict[int, int]:
    """`{YYMMDD: price}` for one player, cached per player per day."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{date.today():%Y%m%d}-{slug}.json"
    if path.exists():
        return {int(k): v for k, v in json.loads(path.read_text()).items()}
    response = requests.get(
        PRICES_URL.format(slug=slug),
        params={"lang": "es", "fields": "*,prices"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()
    history = {int(d): p for d, p in (response.json()["data"].get("prices") or [])}
    path.write_text(json.dumps(history))
    time.sleep(delay)
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--delay", type=float, default=0.5, help="seconds between price reads"
    )
    args = parser.parse_args()

    load_dotenv("packages/biwenger_tools/api/.env")
    biwenger = build_biwenger_session()
    entries = biwenger.get_all_board_messages(
        config.LEAGUE_BOARD_ALL_URL, until_type=SEASON_START_TYPE
    )
    players, _ = BiwengerClient.get_competition_maps(config.ALL_PLAYERS_DATA_URL)
    raw = ac.auctions(entries, my_id=biwenger.user_id)

    rows = []
    for auction in raw:
        slug = (players.get(auction.player_id) or {}).get("slug")
        history = _prices(slug, args.delay) if slug else {}
        rows.append(auction.with_price(ac.price_on(history, auction.closed)))
    priced = [r for r in rows if r.price]

    print(f"\n{len(rows)} market auctions this season, {len(priced)} with a price.\n")

    print("Share of auctions a bid of price × (1 + share) would have won")
    print(f"{'price':>7} {'n':>4} | " + " ".join(f"{f'+{s:.0%}':>5}" for s in SHARES))
    by_band = {}
    for lo, hi, label in BANDS:
        band = [r for r in priced if lo <= r.price < hi]
        by_band[label] = band
        if band:
            cells = " ".join(f"{ac.win_rate(band, s):>5.0%}" for s in SHARES)
            print(f"{label:>7} {len(band):>4} | {cells}")

    print("\nSmallest share that wins the target share of auctions")
    print(f"{'price':>7} | " + " ".join(f"{f'win {t:.0%}':>9}" for t in TARGETS))
    for label, band in by_band.items():
        if band:
            cells = []
            for t in TARGETS:
                need = ac.share_to_win(band, t)
                cells.append(f"{'—' if need is None else f'+{need:.0%}':>9}")
            print(f"{label:>7} | " + " ".join(cells))

    print("\nWhat the auto-bid bids today (auto_bid.py):")
    for tier, share, floor in (
        ("T1", auto_bid.TIER_T1_OVERBID, auto_bid.TIER_ALL_IN_MIN),
        ("T2", auto_bid.TIER_T2_OVERBID, auto_bid.TIER_T2_MIN),
        ("T3", auto_bid.TIER_T3_OVERBID, auto_bid.TIER_T3_MIN),
        ("T4", auto_bid.TIER_T4_OVERBID, auto_bid.TIER_T4_MIN),
    ):
        print(f"  {tier} (SF ≥ {floor}): +{share:.0%}")

    mine = [r for r in priced if r.my_bid is not None]
    won = [r for r in mine if r.won_by_me]
    print(
        f"\nOur auctions: {len(won)} won, {len(mine) - len(won)} lost (a losing bid "
        "only shows when it was among the top three)."
    )
    print(
        "Paid above the next best bid in the ones we won: "
        + _eur(ac.left_on_the_table(priced))
    )
    for r in sorted((r for r in mine if not r.won_by_me), key=lambda r: -r.closed):
        name = (players.get(r.player_id) or {}).get("name", r.player_id)
        print(
            f"  lost {name}: price {_eur(r.price)}, ours {_eur(r.my_bid)}, "
            f"{r.winner_name} won with {_eur(r.winning_bid)} "
            f"(+{r.winning_bid / r.price - 1:.0%})"
        )

    print("\nMedian overbid of each winner, auctions of 5M or more")
    table = ac.overbid_by_winner(priced, 5_000_000)
    for name, (n, share) in sorted(table.items(), key=lambda kv: -kv[1][1]):
        print(f"  {name[:28]:<28} {n:>3} won · median +{share:.0%}")
    if priced:
        print(
            "\nAll auctions: median overbid "
            f"+{median(r.winning_bid / r.price - 1 for r in priced):.0%}"
        )


if __name__ == "__main__":
    main()
