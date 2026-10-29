"""Firestore persistence for the public allowlist: the Telegram user ids the
owner lets read the league's public figures (`/saldos`, `/movimientos`).

One document, `public_members/actual`, like the pact: a short list rewritten
whole on every change, never queried. Not keyed by season — a member stays a
member until the owner removes him with `/publico`.
"""

from core.sdk import firestore as fs
from core.utils import get_logger

logger = get_logger(__name__)

COLLECTION = "public_members"
DOCUMENT = "actual"


def _user_id(raw) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Public member is not a user id.", extra={"entry": repr(raw)})
        return None


def load() -> set[int]:
    """Allowlisted Telegram user ids; empty when nobody was ever added."""
    document = fs.get_document(COLLECTION, DOCUMENT) or {}
    ids = (_user_id(raw) for raw in document.get("user_ids") or [])
    return {user_id for user_id in ids if user_id is not None}


def is_member(chat_id) -> bool:
    """Whether `chat_id` (a private chat: chat id == user id) is allowlisted."""
    user_id = _user_id(chat_id)
    return user_id is not None and user_id > 0 and user_id in load()


def add(user_id: int) -> set[int]:
    members = load() | {int(user_id)}
    fs.set_document(COLLECTION, DOCUMENT, {"user_ids": sorted(members)})
    logger.info("Public member added.", extra={"user_id": int(user_id)})
    return members


def remove(user_id: int) -> set[int]:
    members = load() - {int(user_id)}
    fs.set_document(COLLECTION, DOCUMENT, {"user_ids": sorted(members)})
    logger.info("Public member removed.", extra={"user_id": int(user_id)})
    return members
