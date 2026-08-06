"""Firestore access for the draft, plus the helpers shared across the package.

Every read and write in this package goes through here. One module owning
`fs` is what lets a test swap the whole persistence layer by patching a
single name, and what stops five modules from each holding their own
reference to it.
"""

from typing import Optional

# Re-exported on purpose: every other module reaches Firestore as `store.fs`,
# which is the single seam a test replaces.
from core.sdk import firestore as fs  # noqa: F401

STATE_DOC_ID = "current"
# The turn state is rewritten wholesale on every pick, so anything that must
# survive a pick lives in its own document instead of riding along with it.
LIFECYCLE_DOC_ID = "lifecycle"

PICK_STATUS_RESERVED = "reserved"
PICK_STATUS_APPLIED = "applied"
PICK_STATUS_REVERTED = "reverted"

# Service-level rejections outside `draft.DraftError` — the pure engine
# only knows about pick legality; registration/authorization live here.
ERROR_NOT_REGISTERED = "NOT_REGISTERED"
ERROR_PICK_IN_PROGRESS = "PICK_IN_PROGRESS"
ERROR_BIWENGER_TRANSFER_FAILED = "BIWENGER_TRANSFER_FAILED"
ERROR_DRAFT_CLOSED = "DRAFT_CLOSED"


def _managers_path(season: str) -> str:
    return f"draft/{season}/managers"


def _picks_path(season: str) -> str:
    return f"draft/{season}/picks"


def _state_path(season: str) -> str:
    return f"draft/{season}/state"


def _pick_doc_id(round_num: int, position: int) -> str:
    return f"R{round_num:02d}P{position:02d}"


def _rejected(error: str, message: str) -> dict:
    return {"status": "rejected", "error": error, "message": message}


def _format_wait(seconds: Optional[float]) -> str:
    """A turn's length, in the coarsest unit that still says something.

    A draft runs over days, so seconds are noise and days are the headline.
    """
    if seconds is None:
        return ""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "menos de un minuto"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    unit = "día" if days == 1 else "días"
    return f"{days} {unit} {hours} h" if hours else f"{days} {unit}"


def _eur(amount: int) -> str:
    """Euros as millions, the unit the league actually talks in."""
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")
