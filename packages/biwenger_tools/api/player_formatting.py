"""Player formatting helpers (status, position, play status) shared across renderers."""

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api import config

POSITION_SHORT = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}

# Score type 2 = "SF" (SofaScore-based Automanager rate).
# Used wherever we read predictions from JP.
# The statuses that mean "cannot be fielded at all", as Jornada Perfecta
# spells them. Measured against the live `fitness-daily` payload (533 players
# on 2026-08-08): ok, ok-available, injured, doubt, sanctioned, other. The code
# used to test for "suspended", which JP never sends — the word is `sanctioned`,
# so the branch was dead. It went unnoticed because JP also drops those players
# from its projected XI, and `playerInLineup` caught them one rung lower.
# `doubt` is deliberately absent: JP already prices the doubt into the rate
# (the ten currently doubtful score 2-16 SF) and drops them from the XI.
CANNOT_PLAY = frozenset({"injured", "sanctioned"})

SCORE_SF = 2

# Traffic-light thresholds based on the predicted SF score.
# Tuned by hand against past matchdays; reused by status_emoji().
SF_GREEN_THRESHOLD = 300
SF_YELLOW_THRESHOLD = 100


def short_position(position_id) -> str:
    return POSITION_SHORT.get(position_id, "?")


# Why a player cannot be fielded, in the order the reader cares about. Kept
# apart from the score band on purpose: an injury and a low projection are not
# the same news, and the old traffic light gave them the same colour.
OUT_REASONS = {
    "lesionado": "injured",
    "sancionado": "sanctioned",
    "sin partido": "no match",
}


def availability(jp_player: dict | None) -> str:
    """`"plays"`, `"out"` or `"unknown"` — can he be fielded at all.

    This is the question the row colour should answer, and it is about
    availability rather than expectation. A player JP leaves out of its
    projected eleven is **available**: he comes on at the hour and scores. Only
    an injury, a suspension or no fixture at all make him unfieldable.

    Treating a projected substitute as unavailable was the same mistake one
    layer down as painting a fit starter amber for a modest forecast — his low
    SF already says he will not score much, and the bar column says it.
    """
    if jp_player is None:
        return "unknown"
    if jp_player.get("status") in CANNOT_PLAY:
        return "out"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "out"
    return "plays"


def is_bench(jp_player: dict | None) -> bool:
    """Whether JP leaves him out of its projected eleven.

    A third channel, deliberately independent of `availability` and
    `sf_band`. He is available (he can be fielded) and his projection is
    whatever it is; this answers neither of those questions, and folding it
    into `availability` would corrupt the "14 juegan / 1 no juegan" count
    that reports who is *fit* — the rationale that function already carries.

    Read `playerInLineup` and only that: someone injured is not on the bench,
    he is out, and reporting both about the same player is what makes a
    reader stop trusting either.
    """
    if jp_player is None:
        return False
    if availability(jp_player) != "plays":
        return False
    return ((jp_player.get("nextMatch") or {}).get("playerInLineup")) is False


def count_bench(rows: list[dict]) -> int:
    """How many of these rows JP projects to start on the bench."""
    return sum(is_bench(row.get("jp_player")) for row in rows)


def sf_band(jp_player: dict | None) -> str:
    """`"high"`, `"mid"`, `"low"` or `"none"` for the projected score alone."""
    if jp_player is None:
        return "none"
    sf = get_predict_rate(jp_player, SCORE_SF)
    if sf is None:
        return "none"
    if sf >= SF_GREEN_THRESHOLD:
        return "high"
    if sf >= SF_YELLOW_THRESHOLD:
        return "mid"
    return "low"


def count_availability(rows: list[dict]) -> tuple[int, int, int]:
    """`(plays, out, unknown)` across the rows."""
    plays = out = unknown = 0
    for row in rows:
        state = availability(row.get("jp_player"))
        plays += state == "plays"
        out += state == "out"
        unknown += state == "unknown"
    return plays, out, unknown


def count_bands(rows: list[dict]) -> tuple[int, int, int]:
    """`(high, mid, low)` projected scores **among the players who can play**.

    Counting the rest would drag the reading for no reason: a substitute
    goalkeeper projects near zero every week of the season by design, and a
    torn quadriceps is not a bad forecast.
    """
    high = mid = low = 0
    for row in rows:
        jp = row.get("jp_player")
        if availability(jp) != "plays":
            continue
        band = sf_band(jp)
        high += band == "high"
        mid += band == "mid"
        low += band == "low"
    return high, mid, low


def status_emoji(jp_player: dict | None) -> str:
    """Traffic-light status for a player.

    🔴 injured / sanctioned / no match / not in lineup / SF < 100
    🟡 100 ≤ SF < 300
    🟢 SF ≥ 300
    ⚪ no JP data

    A player JP leaves out of its XI is red only below
    `LINEUP_SUB_STARTS_ABOVE` — above it the optimizer starts him, and an
    image marking him red while the lineup fields him tells the reader two
    different things about the same player on the same morning.
    """
    if jp_player is None:
        return "⚪"
    if jp_player.get("status") in CANNOT_PLAY:
        return "🔴"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "🔴"
    sf = get_predict_rate(jp_player, SCORE_SF)
    if next_match.get("playerInLineup") is False and (
        sf is None or sf <= config.LINEUP_SUB_STARTS_ABOVE
    ):
        return "🔴"
    if sf is None:
        return "🔴"
    if sf >= SF_GREEN_THRESHOLD:
        return "🟢"
    if sf >= SF_YELLOW_THRESHOLD:
        return "🟡"
    return "🔴"


def play_status_label(jp_player: dict | None) -> str:
    if jp_player is None:
        return "sin datos"
    status = jp_player.get("status", "ok")
    if status == "injured":
        return "lesionado"
    if status == "sanctioned":
        return "sancionado"
    if status == "doubt":
        return "duda"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "sin partido"
    if next_match.get("playerInLineup") is False:
        # JP's own field is `playerInLineup`: it says he is not in their
        # *projected eleven*, not that the club left him out of the squad.
        # "No convocado" claimed the stronger thing and was simply wrong.
        return "suplente"
    return "casa" if next_match.get("isLocal") else "fuera"


def sort_key_sf_desc(row: dict):
    """Sort key: players with SF first, then by SF descending."""
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    return (0 if sf is None else 1, sf or 0)


def count_status_buckets(rows: list[dict]) -> tuple[int, int, int, int]:
    """Returns (green, yellow, red, white) counts."""
    green = yellow = red = white = 0
    for row in rows:
        emoji = status_emoji(row.get("jp_player"))
        if emoji == "🟢":
            green += 1
        elif emoji == "🟡":
            yellow += 1
        elif emoji == "🔴":
            red += 1
        else:
            white += 1
    return green, yellow, red, white
