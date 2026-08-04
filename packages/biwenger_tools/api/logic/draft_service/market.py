"""The frozen market: the closed-day CSV joined to Biwenger player ids."""

from typing import Optional
import requests
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from core.sdk.biwenger import BiwengerClient
from packages.biwenger_tools.api.logic import orchestration

logger = get_logger(__name__)


def reset_market_cache() -> None:
    """Drop the cached market so the next call re-reads it."""
    global _MARKET_CACHE
    _MARKET_CACHE = None


def reset_session_cache() -> None:
    """Drop the cached Biwenger session so the next call authenticates again."""
    global _SESSION_CACHE
    _SESSION_CACHE = None


def _with_session(action):
    """Run `action(client)` on a session reused across picks.

    Authenticating is two requests (login + `/account`) against a quota the
    whole league shares, so logging in once per pick was the bulk of the
    draft's traffic. The session token carries no expiry claim, so it is held
    for the life of the instance.

    A rejected token is retried once, and only once. This does not weaken the
    module's no-retry rule: a `401` is refused before Biwenger applies
    anything, so unlike a timeout it cannot have half-happened.
    """
    global _SESSION_CACHE
    if _SESSION_CACHE is None:
        _SESSION_CACHE = orchestration.build_biwenger_session()
    try:
        return action(_SESSION_CACHE)
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 401:
            raise
        logger.info("Biwenger session rejected — re-authenticating once.")
        _SESSION_CACHE = orchestration.build_biwenger_session()
        return action(_SESSION_CACHE)


def _transfer_landed(manager_id: int, player_id: int) -> Optional[bool]:
    """Did the transfer reach Biwenger? `None` when the check itself failed.

    A dropped connection mid-POST is ambiguous: the request may have been
    applied with only the response lost. Biwenger's transfer endpoint carries no
    idempotency key, so guessing either double-buys or strands the pick. One
    read of the manager's squad settles it.
    """
    try:
        squad = _with_session(
            lambda client: client.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        )
    except Exception:
        logger.exception(
            "Could not verify whether the transfer landed.",
            extra={"manager_id": manager_id, "player_id": player_id},
        )
        return None
    return any(int(p.get("id") or 0) == int(player_id) for p in squad)


def _fetch_market_rows() -> list:
    """Frozen CSV rows: an explicit local path wins, otherwise the bucket.

    Production sets no path and reads the bucket copy, so re-uploading a
    corrected export takes effect without a redeploy. Tests and laptop runs
    point at a file, which also keeps the suite off the network.
    """
    if config.DRAFT_MARKET_CSV_PATH:
        return draft.load_market_csv(config.DRAFT_MARKET_CSV_PATH)
    response = requests.get(config.DRAFT_MARKET_CSV_URL, timeout=30)
    response.raise_for_status()
    # Decode explicitly: the bucket serves the CSV without a charset, and
    # `response.text` would then fall back to ISO-8859-1 per the HTTP spec,
    # mangling every accented name and the BOM-prefixed first header.
    return draft.parse_market_csv(response.content.decode("utf-8-sig"))


def _load_market() -> dict:
    """Frozen CSV rows joined to Biwenger ids, keyed by `player_id`.

    Reads the public cf-base player database, which needs no session — so
    resolving a name costs no authentication, and a rejected pick costs
    Biwenger nothing at all.

    Cached per instance: the frozen market cannot change mid-draft, and
    re-reading it on every pick would add a network round-trip to each
    turn. `reset_market_cache` clears it.
    """
    global _MARKET_CACHE
    if _MARKET_CACHE is not None:
        return _MARKET_CACHE

    rows = _fetch_market_rows()
    biwenger_players, teams = BiwengerClient.get_competition_maps(
        config.ALL_PLAYERS_DATA_URL
    )
    matched, unmatched = draft.join_market_to_biwenger(rows, biwenger_players, teams)
    if unmatched:
        logger.warning(
            "Draft market rows unmatched to Biwenger ids.",
            extra={"count": len(unmatched), "names": [r["name"] for r in unmatched]},
        )
    _MARKET_CACHE = {row["player_id"]: row for row in matched}
    return _MARKET_CACHE
