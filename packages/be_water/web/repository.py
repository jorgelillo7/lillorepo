"""Firestore access for be_water: waters catalog + users (favorites).

Collections (project `be-water-app`):
    waters/{water_id}  — one doc per bottled water (see domain.Water)
    users/{nickname}   — {"favorites": [water_id, ...]}
    water_analyses/{water_id}__{analysis_date}
                       — one lab analysis of a water, the browsable history
                         behind the ficha's current composition
    water_revisions/{water_id}__{timestamp}
                       — snapshot of a water taken just before a contribution
                         overwrote its composition, so a bad edit can be undone
                         (scripts/revert_water.py)

`water_analyses` and `water_revisions` answer different questions and are kept
apart on purpose: one is history worth reading, the other is an undo trail with
a `delete_revision`. Merging them would make erasing a typo and erasing a year
the same operation.
"""

from datetime import datetime, timezone

from core.sdk import firestore
from core.utils import get_logger
from packages.be_water.web.domain import Water

logger = get_logger(__name__)

WATERS = "waters"
USERS = "users"
ANALYSES = "water_analyses"
REVISIONS = "water_revisions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_all_waters() -> list[Water]:
    return [
        Water.from_firestore(doc_id, data)
        for doc_id, data in firestore.list_documents(WATERS)
    ]


def get_water(water_id: str) -> Water | None:
    data = firestore.get_document(WATERS, water_id)
    return Water.from_firestore(water_id, data) if data else None


def save_water(water: Water) -> None:
    firestore.set_document(WATERS, water.id, water.to_firestore())
    logger.info("Water saved.", extra={"water_id": water.id})


def save_revision(previous: Water, *, replaced_by: str, reason: str) -> str:
    """Snapshot a water as it stands before an overwrite. Returns the revision
    id. The whole previous document is stored so a revert is a single write."""
    revision_id = f"{previous.id}__{_now_iso()}"
    firestore.set_document(
        REVISIONS,
        revision_id,
        {
            "water_id": previous.id,
            "saved_at": _now_iso(),
            "replaced_by": replaced_by,
            "reason": reason,
            "previous": previous.to_firestore(),
        },
    )
    logger.info(
        "Water revision stored.",
        extra={"water_id": previous.id, "revision_id": revision_id, "reason": reason},
    )
    return revision_id


def analysis_id(water_id: str, analysis_date: str) -> str:
    """The key of one analysis. Keyed by the date the lab did the work, not by
    when it was uploaded, so resubmitting the same label lands on the same
    document and replacing an entry needs no query."""
    return f"{water_id}__{analysis_date}"


def save_analysis(water: Water) -> str:
    """Store this water's composition as the analysis of its `analysis_date`.

    Only ever called for a dated composition — an undated one has no place on a
    timeline and the caller decides that (see `submission.analysis_outcome`).

    The entry carries its own proof: the minerals, which of them a label
    confirmed, where the rest came from, and the photo of that label. A ✓ that
    lived on the ficha instead would end up describing one year's label over
    another year's numbers.
    """
    if not water.analysis_date:
        raise ValueError("save_analysis needs a dated composition")
    entry_id = analysis_id(water.id, water.analysis_date)
    firestore.set_document(
        ANALYSES,
        entry_id,
        {
            "water_id": water.id,
            "analysis_date": water.analysis_date,
            "minerals": water.minerals,
            "verified_fields": water.verified_fields,
            "sources": water.sources,
            "label_photo_url": water.label_photo_url,
            "added_by": water.added_by,
            "added_at": _now_iso(),
        },
    )
    logger.info(
        "Water analysis stored.",
        extra={"water_id": water.id, "analysis_date": water.analysis_date},
    )
    return entry_id


def get_analysis(water_id: str, analysis_date: str) -> dict | None:
    return firestore.get_document(ANALYSES, analysis_id(water_id, analysis_date))


def list_analyses(water_id: str) -> list[dict]:
    """This water's analyses, newest first.

    Sorted on the date string: `YYYY` and `YYYY-MM` compare correctly against
    each other, and a plain year sorts before any month of the same year, which
    is the same ordering `domain.analysis_is_older` applies.
    """
    entries = [
        data
        for _, data in firestore.list_documents(ANALYSES)
        if data.get("water_id") == water_id
    ]
    return sorted(entries, key=lambda e: e.get("analysis_date") or "", reverse=True)


def list_revisions(water_id: str | None = None) -> list[tuple[str, dict]]:
    """(revision_id, data) newest first, optionally for a single water."""
    revisions = [
        (doc_id, data)
        for doc_id, data in firestore.list_documents(REVISIONS)
        if water_id is None or data.get("water_id") == water_id
    ]
    return sorted(revisions, key=lambda pair: pair[1].get("saved_at", ""), reverse=True)


def delete_revision(revision_id: str) -> None:
    firestore.delete_document(REVISIONS, revision_id)
    logger.info("Water revision deleted.", extra={"revision_id": revision_id})


def set_water_sources(water_id: str, sources: dict) -> None:
    """Update only the provenance map, leaving the rest of the doc untouched."""
    firestore.set_document(WATERS, water_id, {"sources": sources}, merge=True)


def set_water_community(water_id: str, community: str) -> None:
    """Update only the community, leaving the rest of the doc untouched."""
    firestore.set_document(WATERS, water_id, {"community": community}, merge=True)


def delete_water(water_id: str) -> None:
    firestore.delete_document(WATERS, water_id)
    logger.info("Water deleted.", extra={"water_id": water_id})


def get_user(nickname: str) -> dict | None:
    return firestore.get_document(USERS, nickname)


def get_all_users() -> dict[str, dict]:
    return dict(firestore.list_documents(USERS))


def ensure_user(nickname: str) -> dict:
    user = get_user(nickname)
    if user is None:
        user = {"favorites": [], "created_at": _now_iso()}
        firestore.set_document(USERS, nickname, user)
        logger.info("User created.", extra={"nickname": nickname})
    return user


def touch_user(nickname: str) -> None:
    """Record activity (last_seen) — called on login and contributions."""
    user = ensure_user(nickname)
    user["last_seen"] = _now_iso()
    firestore.set_document(USERS, nickname, user)


def set_user_blocked(nickname: str, blocked: bool) -> None:
    """Blocked users can't log in or contribute (enforced in the routes)."""
    user = ensure_user(nickname)
    user["blocked"] = blocked
    firestore.set_document(USERS, nickname, user)
    logger.info("User block toggled.", extra={"nickname": nickname, "blocked": blocked})


def toggle_favorite(nickname: str, water_id: str) -> bool:
    """Add/remove a favorite. Returns True if it ended up as favorite."""
    user = ensure_user(nickname)
    favorites = list(user.get("favorites", []))
    if water_id in favorites:
        favorites.remove(water_id)
        is_favorite = False
    else:
        favorites.append(water_id)
        is_favorite = True
    firestore.set_document(USERS, nickname, {"favorites": favorites})
    return is_favorite


def get_favorites(nickname: str, catalog: list[Water]) -> list[Water]:
    user = get_user(nickname)
    if not user:
        return []
    fav_ids = set(user.get("favorites", []))
    return [w for w in catalog if w.id in fav_ids]
