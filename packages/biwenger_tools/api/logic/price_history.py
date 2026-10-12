"""Daily player prices and the streaks read off them. Pure: no I/O.

Biwenger prices move in runs — a player who has risen three days running rose
again over the next three in ~86 % of the cases measured — so the length of
today's run is the trader's whole signal.
"""


def prices_of(players: dict) -> dict[int, int]:
    """`{player id: cf-base price}` for every priced player in the players map."""
    return {
        int(p["id"]): int(p["price"])
        for p in players.values()
        if p.get("id") is not None and p.get("price")
    }


def streak(history: list[dict[int, int]], player_id: int) -> int:
    """Consecutive daily moves in one direction ending on the newest day:
    `+n` rises, `-n` falls, `0` when today was flat or there is no history.

    `history` runs oldest to newest. A day the player is missing from ends the
    run rather than bridging it — an absent price is not a move.
    """
    run = 0
    for older, newer in zip(reversed(history[:-1]), reversed(history)):
        before, after = older.get(player_id), newer.get(player_id)
        if before is None or after is None or before == after:
            break
        step = 1 if after > before else -1
        if run and (run > 0) != (step > 0):
            break
        run += step
    return run
