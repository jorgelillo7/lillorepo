"""Firestore persistence for the public allowlist: the Telegram chats the
owner lets read the league's public figures (`/saldos`, `/movimientos`) — a
mate's private chat, or a group the owner opened with him.

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
    """Whether `chat_id` is allowlisted: a member's private chat (his user id)
    or a group the owner added by its own id."""
    user_id = _user_id(chat_id)
    return user_id is not None and user_id in load()


# Chats that wrote without being members, offered in `/publico` so the owner
# can authorize a group without looking its id up. Newest kept, a handful.
_PENDING_MAX = 10


def load_pending() -> dict[int, str]:
    """`{chat_id: title}` of the chats that asked lately and are not members."""
    document = fs.get_document(COLLECTION, DOCUMENT) or {}
    out = {}
    for entry in document.get("pending") or []:
        chat_id = _user_id((entry or {}).get("chat_id"))
        if chat_id is not None:
            out[chat_id] = str(entry.get("title") or chat_id)
    return out


def remember_pending(chat_id: int, title: str) -> None:
    """Note a chat that asked without being a member. Never answers it."""
    document = fs.get_document(COLLECTION, DOCUMENT) or {}
    pending = [
        e
        for e in document.get("pending") or []
        if _user_id(e.get("chat_id")) != chat_id
    ]
    pending.insert(0, {"chat_id": int(chat_id), "title": title or str(chat_id)})
    fs.set_document(
        COLLECTION, DOCUMENT, {"pending": pending[:_PENDING_MAX]}, merge=True
    )


def load_names() -> dict[int, str]:
    """Labels the owner gave members by hand, keyed by user id."""
    document = fs.get_document(COLLECTION, DOCUMENT) or {}
    out = {}
    for raw, name in (document.get("names") or {}).items():
        user_id = _user_id(raw)
        if user_id is not None and name:
            out[user_id] = str(name)
    return out


def _save(members: set[int], names: dict[int, str]) -> None:
    pending = [
        {"chat_id": k, "title": v}
        for k, v in load_pending().items()
        if k not in members
    ]
    fs.set_document(
        COLLECTION,
        DOCUMENT,
        {
            "user_ids": sorted(members),
            "names": {str(k): v for k, v in names.items() if k in members},
            "pending": pending,
        },
    )


def add(user_id: int, name: str | None = None) -> set[int]:
    """Add a member; `name` labels him in `/publico` when given, else the
    title the chat had when it was remembered as pending."""
    members = load() | {int(user_id)}
    names = load_names()
    label = name or load_pending().get(int(user_id))
    if label:
        names[int(user_id)] = label
    _save(members, names)
    logger.info("Public member added.", extra={"user_id": int(user_id)})
    return members


def remove(user_id: int) -> set[int]:
    members = load() - {int(user_id)}
    _save(members, load_names())
    logger.info("Public member removed.", extra={"user_id": int(user_id)})
    return members
