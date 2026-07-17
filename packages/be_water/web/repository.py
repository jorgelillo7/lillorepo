"""Firestore access for be_water: waters catalog + users (favorites).

Collections (project `be-water-app`):
    waters/{water_id}  — one doc per bottled water (see domain.Water)
    users/{nickname}   — {"favorites": [water_id, ...]}
"""

from core.sdk import firestore
from core.utils import get_logger
from packages.be_water.web.domain import Water

logger = get_logger(__name__)

WATERS = "waters"
USERS = "users"


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


def get_user(nickname: str) -> dict | None:
    return firestore.get_document(USERS, nickname)


def ensure_user(nickname: str) -> dict:
    user = get_user(nickname)
    if user is None:
        user = {"favorites": []}
        firestore.set_document(USERS, nickname, user)
        logger.info("User created.", extra={"nickname": nickname})
    return user


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
