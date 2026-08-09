"""Log the provider values we do not model, so the next surprise arrives dated.

Three defects this month were the same shape: the code held a rule the game
does not have. A formation list two entries short, a squad shape assumed, and
a status branch testing for `suspended` — a word Jornada Perfecta never sends.
Each was found by someone eventually noticing, months later.

This notices instead. It changes no decision and returns nothing; it writes a
log line when reality steps outside what has actually been observed, which is
the moment the knowledge is cheapest to capture.

The two sets below are **what has been seen in the wild**, not what the code
handles — the distinction that matters. `break` is handled by `lineup._sf` and
has never once been observed in 533 players, so its first appearance is
precisely the event worth logging.
"""

from core.utils import get_logger

logger = get_logger(__name__)

# Measured on the live `fitness-daily` payload, 533 players, 2026-08-08.
OBSERVED_JP_STATUS = frozenset(
    {"ok", "ok-available", "injured", "doubt", "sanctioned", "other"}
)
# Every player reported `pending`; the season had not started. `break` is
# handled but unseen, so its first sighting answers a standing question.
OBSERVED_FIXTURE_STATUS = frozenset({"pending"})

# Biwenger's own vocabulary, from the competition payload the same day. Mapped
# onto "can this player be fielded", so the two providers can be compared at
# all — they use different words for the same states.
_BIWENGER_OUT = frozenset({"injured", "sanctioned", "discarded"})
_JP_OUT = frozenset({"injured", "sanctioned"})


def observe(rows: list) -> None:
    """Log anything unmodelled in these rows. Never raises, never decides.

    Called from the lineup path because that is the decision that reaches
    Biwenger unattended every morning; a wrong reading there costs points
    nobody is watching for.
    """
    try:
        for row in rows:
            jp = row.get("jp_player") or {}
            if not jp:
                continue
            _watch_status(row, jp)
            _watch_fixture(row, jp)
            _watch_disagreement(row, jp)
    except Exception:  # pragma: no cover - an observer must never break a lineup
        logger.warning("Provider watch failed; lineup unaffected.", exc_info=True)


def log_promotions(promotions: list) -> None:
    """Log every promoted substitute who made the starting XI.

    Neither provider exposes whether a promoted bet actually paid off on the
    paths this code walks, so this records the bet rather than grading it:
    one line per promotion, with the certain starter he displaced from his
    line — the counterfactual a later audit needs to check the promotion
    against the round's real points. Never raises, never decides.
    """
    try:
        for promo in promotions:
            logger.warning(
                "Uncalled substitute promoted into the lineup.",
                extra={
                    "player": promo.get("player"),
                    "projection": promo.get("projection"),
                    "threshold": promo.get("threshold"),
                    "position": promo.get("position"),
                    "displaced_player": promo.get("displaced_player"),
                    "displaced_sf": promo.get("displaced_sf"),
                },
            )
    except Exception:  # pragma: no cover - an observer must never break a lineup
        logger.warning("Provider watch failed; lineup unaffected.", exc_info=True)


def _watch_status(row: dict, jp: dict) -> None:
    status = jp.get("status")
    if status is not None and status not in OBSERVED_JP_STATUS:
        logger.warning(
            "JP status never seen before.",
            extra={"player": row.get("name"), "status": status},
        )


def _watch_fixture(row: dict, jp: dict) -> None:
    status = (jp.get("nextMatch") or {}).get("status")
    if status is not None and status not in OBSERVED_FIXTURE_STATUS:
        logger.warning(
            "Fixture status never seen before — check what it means for scoring.",
            extra={"player": row.get("name"), "fixture_status": status},
        )


def _watch_disagreement(row: dict, jp: dict) -> None:
    """Biwenger and JP disagreeing on availability is rare and load-bearing.

    Measured at 1 in 481 on 2026-08-08: JP called Moussa Diarra `ok` while
    Biwenger had him injured with an indefinite return. A player like that is
    fielded and scores nothing. Too rare to justify overriding one source with
    the other on this evidence — but not too rare to write down each time it
    happens, which is how that decision eventually gets made with numbers.
    """
    bw_status = row.get("bw_status")
    if bw_status is None:
        return
    if (jp.get("status") in _JP_OUT) != (bw_status in _BIWENGER_OUT):
        logger.warning(
            "Providers disagree on availability.",
            extra={
                "player": row.get("name"),
                "jp_status": jp.get("status"),
                "biwenger_status": bw_status,
                "biwenger_note": row.get("bw_status_info"),
            },
        )
