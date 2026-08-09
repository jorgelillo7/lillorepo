"""The turn state and the draft lifecycle — the two documents that say
where the draft is and whether it is still open."""

import time
from typing import Optional
from packages.biwenger_tools.constants import LEAGUE_MEMBERS
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from . import store
from .store import (
    ERROR_DRAFT_CLOSED,
    LIFECYCLE_DOC_ID,
    STATE_DOC_ID,
    _eur,
    _managers_path,
    _rejected,
    _state_path,
)

logger = get_logger(__name__)


def load_state() -> draft.DraftState:
    data = store.fs.get_document(_state_path(config.DRAFT_SEASON), STATE_DOC_ID)
    return draft.new_draft_state() if data is None else draft.state_from_dict(data)


def _save_state(
    state: draft.DraftState, turn_started_at: Optional[float] = None
) -> None:
    doc = draft.state_to_dict(state)
    if turn_started_at is not None:
        doc["turn_started_at"] = turn_started_at
    store.fs.set_document(_state_path(config.DRAFT_SEASON), STATE_DOC_ID, doc)


def lifecycle() -> dict:
    """Draft lifecycle record: `{opened_at, closed, closed_at}`.

    Absent means open. A draft that predates this record must keep working —
    the guard exists to stop writes *after* the last pick, not to demand a
    ceremony the running draft never performed.
    """
    return (
        store.fs.get_document(_state_path(config.DRAFT_SEASON), LIFECYCLE_DOC_ID) or {}
    )


def _reject_if_closed() -> Optional[dict]:
    """Rejection for a write on a finished draft, or None while it is live.

    `/deshacer` reverts a real Biwenger transfer with real money. Once the
    season starts, that is not an undo — it is selling a player mid-season.
    """
    if not lifecycle().get("closed"):
        return None
    return _rejected(
        ERROR_DRAFT_CLOSED,
        "El draft está cerrado. Las operaciones sobre Biwenger quedan "
        "bloqueadas: un fichaje o un deshacer ahora movería dinero real de "
        "la temporada en curso.",
    )


def close_draft(reason: str = "completed") -> None:
    """Mark the draft finished. Idempotent."""
    if lifecycle().get("closed"):
        return
    store.fs.set_document(
        _state_path(config.DRAFT_SEASON),
        LIFECYCLE_DOC_ID,
        {"closed": True, "closed_at": time.time(), "closed_reason": reason},
        merge=True,
    )
    logger.info("Draft closed.", extra={"season": config.DRAFT_SEASON, "why": reason})


def open_draft(csv_url: str = "") -> dict:
    """Open the draft and stamp the starting instant.

    `turn_started_at` is set here so the first pick has something to measure
    against. Without it the wait times only begin once someone picks, which is
    how the 26-27 draft lost every timing before pick 49.
    """
    now = time.time()
    store.fs.set_document(
        _state_path(config.DRAFT_SEASON),
        LIFECYCLE_DOC_ID,
        {"closed": False, "opened_at": now, "csv_url": csv_url},
        merge=True,
    )
    _save_state(load_state(), turn_started_at=now)
    logger.info("Draft opened.", extra={"season": config.DRAFT_SEASON})
    return {"status": "ok", "opened_at": now, "season": config.DRAFT_SEASON}


def get_state() -> dict:
    """Current turn + per-manager budgets/spend/squad size, name-keyed."""
    state = load_state()
    turn = draft.whose_turn(state)
    completed = turn is None
    pick_num = draft.current_pick_number(state)
    total_picks = len(state.order) * draft.NUM_ROUNDS

    if completed:
        last = state.picks[-1] if state.picks else None
        round_num = last.round if last else 0
        position = last.position if last else 0
        manager_name = ""
        message = "🏁 El draft ha terminado. ¡Gracias por jugar!"
    else:
        round_num, position, _ = draft.pick_number_to_slot(pick_num, state.order)
        manager_name = LEAGUE_MEMBERS.get(turn, str(turn))
        upcoming = [
            LEAGUE_MEMBERS.get(m, str(m))
            for m in (
                draft.pick_number_to_slot(n, state.order)[2]
                for n in range(pick_num + 1, min(pick_num + 3, total_picks + 1))
            )
        ]
        lines = [
            f"🏁 <b>Draft {config.DRAFT_SEASON}</b> — Ronda "
            f"{round_num}/{draft.NUM_ROUNDS} · Pick {pick_num}/{total_picks}",
            f"🎯 Le toca a {mention(turn)}",
        ]
        if upcoming:
            lines.append(f"⏭️ Después: {' → '.join(upcoming)}")
        lines.append("")
        lines.append("💰 <b>Libres</b> · plantilla")
        for m in state.order:
            free = state.budgets.get(m, 0) - state.spent.get(m, 0)
            lines.append(
                f"  {LEAGUE_MEMBERS.get(m, str(m))} — {_eur(free)} · "
                f"{len(state.squads.get(m, []))}/{draft.SQUAD_SIZE}"
            )
        message = "\n".join(lines)

    budgets = {LEAGUE_MEMBERS.get(m, str(m)): v for m, v in state.budgets.items()}
    spent = {LEAGUE_MEMBERS.get(m, str(m)): v for m, v in state.spent.items()}
    squad_counts = {
        LEAGUE_MEMBERS.get(m, str(m)): len(squad) for m, squad in state.squads.items()
    }

    return {
        "completed": completed,
        "pick_number": pick_num,
        "round": round_num,
        "position": position,
        "manager_id": turn,
        "manager_name": manager_name,
        "budgets": budgets,
        "spent": spent,
        "squad_counts": squad_counts,
        "message": message,
    }


def mention(manager_id: int) -> str:
    """HTML mention of the manager's registered Telegram user.

    A `tg://user?id=` link makes Telegram actually notify the person on
    turn, username or not. Falls back to the plain name when the manager
    has not done `/soy` yet — a dead link would notify nobody anyway.
    """
    name = LEAGUE_MEMBERS.get(manager_id, str(manager_id))
    for _, data in store.fs.list_documents(_managers_path(config.DRAFT_SEASON)):
        if int(data.get("manager_id") or 0) == manager_id:
            return f'<a href="tg://user?id={data["telegram_user_id"]}">{name}</a>'
    return name
