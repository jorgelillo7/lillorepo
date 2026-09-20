"""This league's real ("Personalizado") points, reconstructed from raw stats.

Moved here from the draft skill's `fetch_real_points.py` so the projection
grading script can reuse it without importing a skill script — the rule the
skill's own `BUILD.bazel` already states for `draft.py`'s composition check:
one definition, imported, not restated.
"""

# Biwenger position ids.
GK, DEF = 1, 2

# A start, not an appearance: below this a player came off the bench, and
# the league's play/win bonuses only trigger past 65 minutes anyway.
STARTER_MINUTES = 60


def personalizado(reports: list, position: int) -> dict:
    """This league's custom total from per-match `rawStats`.

    Verified to the point against two controls of different lines: Vinícius
    Jr 330 (forward, 296 SofaScore base) and Joan García 274 (goalkeeper, 190).

    Biwenger's `star` flag is deliberately ignored — including it as the
    config's MVP bonus overshoots both controls (345 and 277).
    """
    total = base = games = minutes = wins = clean = started = 0
    for report in reports:
        stats = report.get("rawStats") or {}
        played = stats.get("minutesPlayed") or 0
        if not played:
            continue
        games += 1
        minutes += played
        if played >= STARTER_MINUTES:
            started += 1
        score = stats.get("score2") or 0
        base += score
        points = score
        # Being on the pitch is worth points by itself, and again if the team
        # wins — the single biggest reason a starter beats a better substitute.
        if played > 65:
            points += 1
            if stats.get("win"):
                points += 1
                wins += 1
            if stats.get("lost"):
                points -= 1
        if stats.get("cleanSheet"):
            clean += 1
            points += 2 if position == GK else (1 if position == DEF else 0)
        points -= stats.get("yellowCard") or 0
        points -= stats.get("goalsPenalty") or 0  # a penalty goal scores less
        points -= 2 * (stats.get("penaltyMissed") or 0)
        if position == GK:
            points += (stats.get("goals") or 0) + 2 * (stats.get("assists") or 0)
        elif position == DEF:
            points += stats.get("assists") or 0
        total += points
    return {
        "points": total,
        "sofascore_real": base,
        "games": games,
        "starts": started,
        "minutes": minutes,
        "wins": wins,
        "clean_sheets": clean,
    }


def reports_for_round(reports: list, round_id: int) -> list:
    """The subset of `reports` that belong to one specific round.

    `personalizado` sums over whatever list it is handed; grading a single
    matchday needs that matchday isolated first, or it silently reports the
    player's whole season instead of the round being graded. A report with
    no `match.round` (malformed, or a preview fixture with no report yet)
    cannot belong to any round, so it is dropped rather than raising.
    """
    return [
        report
        for report in reports or []
        if ((report.get("match") or {}).get("round") or {}).get("id") == round_id
    ]


def missing_reports(fielded_ids: list, points: dict, counted: dict) -> list:
    """The fielded players no report actually backs.

    `personalizado` sums whatever list it is handed, so no reports scores 0 —
    the same number as a player who had a dreadful afternoon. A backfill once
    printed `0 pts reales` across eight rounds because an upstream field
    selector had gone stale and every report arrived empty, and nothing in
    the output distinguished that from a genuinely terrible squad.

    `counted` says how many reports each player's total was computed from,
    and it is the only thing that separates the two. An earlier version of
    this asked whether the id was *present* — which it always is, carrying
    its zero — and a split round walked straight through: Biwenger files a
    postponed match under a different round id, so the original came back as
    eleven exact zeros and would have been stored as a matchday.

    Scoring nothing is an answer. Having nothing to score is not.
    """
    return [
        player_id
        for player_id in fielded_ids
        if player_id not in points or not (counted or {}).get(player_id)
    ]
