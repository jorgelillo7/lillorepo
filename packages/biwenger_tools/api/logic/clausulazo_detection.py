"""Read-side helpers for `/emergencia`: who got clausulated and which
position the squad needs reinforcing.

Sibling of `clausulazo_candidates.py` (which builds the rival pool to
clausulazo *to*). The split keeps "what's happening" (this file)
separate from "who I can go after" (candidates).

Public surface:

- `recent_lost_players(...)` — every clausulazo against me in the
  configured window, resolved against the cf-base players map. Returns
  a list because Biwenger batches transfers under a single shared
  `date` and we can't reliably tell which is the most recent within a
  batch — that's a caller decision.
- `weakest_outfield_position(...)` — DEF/MID/FWD with the fewest
  players in my squad, with DEF > MID > FWD tie-break.
- `unique_outfield_positions(losses)` — DEF/MID/FWD positions a loss
  list touches (primary + alts).
- `is_multi_position(bw_player)` — `altPositions` non-empty.
"""

from core.sdk.biwenger import BiwengerClient
from core.utils import get_logger
from packages.biwenger_tools.api import config

logger = get_logger(__name__)

RECENT_CLAUSULAZO_WINDOW_SECONDS = 24 * 60 * 60

# Outfield positions, in DEF > MID > FWD priority order. GK is out of
# scope: we never clausulazo a GK on emergency and we never reinforce
# the GK line via /emergencia either.
OUTFIELD_POSITION_IDS = (2, 3, 4)


def is_multi_position(bw_player: dict) -> bool:
    """A multi-position player has at least one `altPositions` entry."""
    return bool(bw_player.get("altPositions") or [])


def recent_lost_players(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    my_manager_name: str,
    now_epoch: float,
) -> list[dict]:
    """Every clausulazo against me in the last
    `RECENT_CLAUSULAZO_WINDOW_SECONDS`, resolved against `biwenger_players`.

    Returns `[{player_id, name, position_id, alt_positions, date}, ...]`
    in board order. Biwenger packs multiple transfers into a single
    entry with one shared `date`, so the order here is NOT chronological
    — when there's more than one match the caller is the one that
    decides what to do (typically: show a selector so the user picks).

    Detection compares `from.id == biwenger.user_id` first; some board
    payload variants only expose `from.name`, so we fall back to a
    name match. Either suffices — we own both sides of the lookup.
    """
    raw = biwenger.get_all_clausulazos(config.CLAUSULAZOS_URL)
    entries = raw.get("data", []) or []
    if isinstance(entries, dict):
        entries = list(entries.values())

    cutoff = now_epoch - RECENT_CLAUSULAZO_WINDOW_SECONDS
    losses: list[dict] = []
    for entry in entries:
        entry_date = entry.get("date", 0) or 0
        if entry_date < cutoff:
            continue
        for item in entry.get("content") or []:
            if item.get("type") != "clause":
                continue
            from_obj = item.get("from") or {}
            from_id = from_obj.get("id")
            from_name = from_obj.get("name")
            is_me = (from_id is not None and int(from_id) == int(biwenger.user_id)) or (
                from_name and my_manager_name and from_name == my_manager_name
            )
            if not is_me:
                continue
            player_ref = item.get("player")
            player_id = (
                player_ref.get("id") if isinstance(player_ref, dict) else player_ref
            )
            bw_player = biwenger_players.get(player_id)
            if not bw_player:
                continue
            losses.append(
                {
                    "player_id": player_id,
                    "name": bw_player.get("name"),
                    "position_id": bw_player.get("position"),
                    "alt_positions": bw_player.get("altPositions") or [],
                    "date": entry_date,
                }
            )
    return losses


def unique_outfield_positions(losses: list[dict]) -> list[int]:
    """Outfield positions a loss list touches (primary + alts), DEF/MID/FWD order.

    Used to build the selector buttons when there's more than one
    recent loss against me: one button per distinct position the
    losses imply. GK is excluded (see module docstring).
    """
    found: set[int] = set()
    for loss in losses:
        for pos in (loss["position_id"], *loss["alt_positions"]):
            if pos in OUTFIELD_POSITION_IDS:
                found.add(pos)
    return [p for p in OUTFIELD_POSITION_IDS if p in found]


def weakest_outfield_position(my_squad: list, biwenger_players: dict) -> int:
    """Position id with the fewest players among DEF/MID/FWD.

    Ties break in DEF > MID > FWD order — lower-tier positions get
    filled first because affordable replacements are easier to find.
    """
    counts = {pos: 0 for pos in OUTFIELD_POSITION_IDS}
    for entry in my_squad:
        bw_player = biwenger_players.get(entry.get("id"))
        if not bw_player:
            continue
        pos = bw_player.get("position")
        if pos in counts:
            counts[pos] += 1
    return min(OUTFIELD_POSITION_IDS, key=lambda pos: (counts[pos], pos))
