"""Who is allowed to pick: the `/soy` roll-call and its Telegram bindings."""

from typing import Optional
from core.constants import LEAGUE_MEMBERS
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from packages.biwenger_tools.api.logic.player_matching import normalize_name
from . import state, store
from .store import _managers_path

logger = get_logger(__name__)


def _resolve_manager_name(name: str) -> Optional[int]:
    """Resolve free-text `name` to a manager id among `draft.DEFAULT_ORDER`.

    Exact match or unambiguous prefix, accent/case-insensitive. A name that
    only matches a `LEAGUE_MEMBERS` spectator (not in the draft order) never
    resolves.
    """
    norm = normalize_name(name)
    if not norm:
        return None
    matches = [
        manager_id
        for manager_id in draft.DEFAULT_ORDER
        if normalize_name(LEAGUE_MEMBERS.get(manager_id, "")).startswith(norm)
    ]
    return matches[0] if len(matches) == 1 else None


def list_draft_managers() -> dict:
    """Every manager in the draft order, with who has claimed each one.

    Backs the `/soy` picker: typing the name by hand is the error-prone path
    when seven people register at once.
    """
    claimed = {
        int(data["manager_id"]): data.get("telegram_user_id", "")
        for _, data in store.fs.list_documents(_managers_path(config.DRAFT_SEASON))
        if data.get("manager_id") is not None
    }
    managers = [
        {
            "manager_id": mid,
            "name": LEAGUE_MEMBERS.get(mid, str(mid)),
            "claimed_by": claimed.get(mid, ""),
        }
        for mid in state.load_state().order
    ]
    free = [m["name"] for m in managers if not m["claimed_by"]]
    message = (
        "👤 <b>¿Quién eres?</b> Pulsa tu nombre."
        if free
        else "👥 Todos los managers están ya registrados."
    )
    return {"managers": managers, "message": message}


def register_manager(
    telegram_user_id: str, name: str = "", manager_id: Optional[int] = None
) -> dict:
    """Bind a Telegram user id to a draft manager, by id or by name.

    The two entry points carry different intent. `manager_id` is the picker:
    its buttons stay tappable in the chat and are not bound to any user, so a
    stray tap on somebody else's name must never silently reassign a user who
    is already registered — that is exactly how a round of button-mashing
    erased half the roll-call. Re-tapping your own name is a harmless no-op.
    `name` is typed `/soy <nombre>`: explicit intent, so it may overwrite (a
    manager correcting a mistake shouldn't need an admin). Claiming a manager
    somebody else holds is allowed but reported, so the group sees the change.
    """
    via_picker = manager_id is not None
    if via_picker:
        manager_id = (
            int(manager_id) if int(manager_id) in state.load_state().order else None
        )
    else:
        manager_id = _resolve_manager_name(name)

    if via_picker and manager_id is not None:
        mine = _get_registered_manager(telegram_user_id)
        if mine and int(mine.get("manager_id") or 0) != manager_id:
            current = mine.get("manager_name", "?")
            return {
                "ok": False,
                "manager_id": int(mine["manager_id"]),
                "manager_name": current,
                "message": (
                    f"Ya estás registrado como <b>{current}</b>. Para cambiar, "
                    f"escribe <code>/soy {LEAGUE_MEMBERS[manager_id]}</code>."
                ),
            }
    if manager_id is None:
        return {
            "ok": False,
            "manager_id": None,
            "manager_name": "",
            "message": (
                f"No encuentro a «{name}» entre los managers del draft. "
                "Escribe <code>/soy</code> a secas y elige de la lista."
            ),
        }
    previous = next(
        (
            data.get("telegram_user_id", "")
            for _, data in store.fs.list_documents(_managers_path(config.DRAFT_SEASON))
            if int(data.get("manager_id") or 0) == manager_id
            and str(data.get("telegram_user_id")) != str(telegram_user_id)
        ),
        "",
    )
    manager_name = LEAGUE_MEMBERS[manager_id]
    store.fs.set_document(
        _managers_path(config.DRAFT_SEASON),
        str(telegram_user_id),
        {
            "telegram_user_id": str(telegram_user_id),
            "manager_id": manager_id,
            "manager_name": manager_name,
        },
    )
    note = " (antes lo tenía otra cuenta)" if previous else ""
    return {
        "ok": True,
        "manager_id": manager_id,
        "manager_name": manager_name,
        "message": f"✅ Registrado como <b>{manager_name}</b>{note}.",
    }


def _get_registered_manager(telegram_user_id: str) -> Optional[dict]:
    return store.fs.get_document(
        _managers_path(config.DRAFT_SEASON), str(telegram_user_id)
    )
