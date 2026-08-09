"""Reserving, applying and undoing a pick — everything that can move a
player in Biwenger, and the public entry points the bot calls."""

import time
from typing import Optional
from packages.biwenger_tools.constants import LEAGUE_MEMBERS
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from . import store
from .store import (
    ERROR_BIWENGER_TRANSFER_FAILED,
    ERROR_NOT_REGISTERED,
    ERROR_PICK_IN_PROGRESS,
    PICK_STATUS_APPLIED,
    PICK_STATUS_RESERVED,
    PICK_STATUS_REVERTED,
    STATE_DOC_ID,
    _eur,
    _format_wait,
    _pick_doc_id,
    _picks_path,
    _rejected,
    _state_path,
)
from .managers import _get_registered_manager
from .market import _load_market, _transfer_landed, _with_session
from .state import _reject_if_closed, _save_state, close_draft, load_state, mention

logger = get_logger(__name__)


def _reserve_pick(manager_id: int, player_id: int, players_by_id: dict) -> dict:
    """Validate the pick and, if legal, atomically reserve its slot.

    Returns one of:
      `{"outcome": "invalid", "error": ..., "message": ...}`
      `{"outcome": "duplicate", "pick": <existing pick doc>}`
      `{"outcome": "reserved", "pick": <new pick doc>}`

    The deterministic `R{round}P{position}` doc id is derived from the
    persisted state's current pick number, read inside the same
    transaction — so two concurrent requests for the same slot can only
    ever have one of them win the `create`, and the loser comes back as
    "duplicate" rather than racing a second Biwenger call.
    """
    season = config.DRAFT_SEASON

    def txn(transaction):
        client = store.fs.get_client()
        state_ref = client.collection(_state_path(season)).document(STATE_DOC_ID)
        state_snapshot = state_ref.get(transaction=transaction)
        state = (
            draft.state_from_dict(state_snapshot.to_dict())
            if state_snapshot.exists
            else draft.new_draft_state()
        )

        result = draft.validate_pick(state, manager_id, player_id, players_by_id)
        if not result.ok:
            return {
                "outcome": "invalid",
                "error": result.error.name,
                "message": result.message,
            }

        pick_num = draft.current_pick_number(state)
        round_num, position, _ = draft.pick_number_to_slot(pick_num, state.order)
        doc_id = _pick_doc_id(round_num, position)
        pick_ref = client.collection(_picks_path(season)).document(doc_id)
        existing = pick_ref.get(transaction=transaction)
        # A reverted slot is free again: undo rewinds the turn to the same
        # manager, who then re-picks into this very doc id. Only `reserved` and
        # `applied` mean "already in flight" and must block a second call.
        if (
            existing.exists
            and (existing.to_dict() or {}).get("status") != PICK_STATUS_REVERTED
        ):
            return {"outcome": "duplicate", "pick": existing.to_dict()}

        row = players_by_id[player_id]
        pick_doc = {
            "round": round_num,
            "position": position,
            "global_pick": pick_num,
            "manager_id": manager_id,
            "manager_name": LEAGUE_MEMBERS.get(manager_id, str(manager_id)),
            "player_id": player_id,
            "player_name": row.get("name"),
            "player_team": row.get("team"),
            "price": int(row.get("price") or 0),
            "status": PICK_STATUS_RESERVED,
            "applied_to_biwenger": False,
        }
        transaction.set(pick_ref, pick_doc)
        return {"outcome": "reserved", "pick": pick_doc}

    return store.fs.run_transaction(txn)


def _finalize_pick(manager_id: int, player_id: int, players_by_id: dict) -> tuple:
    """Apply the (already-reserved, already-validated) pick to `DraftState`.

    Returns `(new_state, waited_seconds)`. `waited_seconds` is how long this
    manager sat on the clock, and is `None` for the opening pick, which has no
    preceding turn to measure from.

    `turn_started_at` rides on the state document but deliberately not on
    `DraftState`: the pure engine has no business knowing about clocks. It has
    to be written in the same `set` as the state — that call replaces the whole
    document, so a separate write would be wiped by the next pick.
    """

    def txn(transaction):
        client = store.fs.get_client()
        state_ref = client.collection(_state_path(config.DRAFT_SEASON)).document(
            STATE_DOC_ID
        )
        state_snapshot = state_ref.get(transaction=transaction)
        stored = state_snapshot.to_dict() if state_snapshot.exists else None
        state = draft.state_from_dict(stored) if stored else draft.new_draft_state()
        started_at = (stored or {}).get("turn_started_at")
        new_state, result = draft.apply_pick(
            state, manager_id, player_id, players_by_id
        )
        if not result.ok:
            # Reservation already validated this exact pick moments ago with
            # nothing else able to advance `state` in between — this branch
            # is unreachable in practice, kept as a defensive backstop.
            logger.error(
                "Pick failed to apply after a successful reservation.",
                extra={"manager_id": manager_id, "player_id": player_id},
            )
            return state, None
        now = time.time()
        transaction.set(
            state_ref, {**draft.state_to_dict(new_state), "turn_started_at": now}
        )
        waited = round(now - started_at) if started_at else None
        return new_state, waited

    return store.fs.run_transaction(txn)


def _duplicate_pick_response(pick_doc: dict) -> dict:
    manager_name = pick_doc.get("manager_name") or str(pick_doc.get("manager_id"))
    player_name = pick_doc.get("player_name") or pick_doc.get("player_id")

    if pick_doc.get("status") == PICK_STATUS_APPLIED:
        state = load_state()
        manager_id = pick_doc.get("manager_id")
        remaining = state.budgets.get(manager_id, 0) - state.spent.get(manager_id, 0)
        next_manager_id = draft.whose_turn(state)
        next_manager = (
            LEAGUE_MEMBERS.get(next_manager_id, "")
            if next_manager_id is not None
            else ""
        )
        return {
            "status": "applied",
            "message": (
                f"Ese fichaje ya se aplicó antes: {manager_name} fichó a "
                f"{player_name}. No repito la llamada a Biwenger."
            ),
            "player": {
                "player_id": pick_doc.get("player_id"),
                "name": pick_doc.get("player_name"),
                "team": pick_doc.get("player_team"),
                "price": pick_doc.get("price"),
            },
            "remaining": remaining,
            "next_manager": next_manager,
        }

    # status == "reserved": a previous attempt crashed between reserving the
    # slot and confirming it with Biwenger. Retrying blindly risks charging
    # twice, so this needs a human to check Biwenger directly.
    return {
        "status": "rejected",
        "error": ERROR_PICK_IN_PROGRESS,
        "message": (
            f"El fichaje de {manager_name} ({player_name}) quedó a medias — "
            "reservado pero sin confirmar en Biwenger. No reintento en automático "
            "para no cobrar dos veces; comprueba Biwenger y avisa al admin."
        ),
    }


def _applied_response(
    new_state: draft.DraftState,
    manager_id: int,
    player_id: int,
    players_by_id: dict,
    price: int,
    applied_to_biwenger: bool,
    waited_seconds: Optional[float] = None,
) -> dict:
    manager_name = LEAGUE_MEMBERS.get(manager_id, str(manager_id))
    remaining = new_state.budgets.get(manager_id, 0) - new_state.spent.get(
        manager_id, 0
    )
    next_manager_id = draft.whose_turn(new_state)
    next_manager = (
        LEAGUE_MEMBERS.get(next_manager_id, "") if next_manager_id is not None else ""
    )
    row = players_by_id[player_id]

    sim_note = (
        "" if applied_to_biwenger else " (modo simulación: Biwenger no se ha tocado)"
    )
    if next_manager_id is None:
        # Nobody left to pick: shut the door behind the last one so a stray
        # `/deshacer` in October cannot sell a player mid-season.
        close_draft()
        turn_note = (
            "🏁 ¡Draft completado! Fichajes y deshacer quedan bloqueados: "
            "a partir de ahora se opera desde la app."
        )
    else:
        turn_note = f"🎯 Turno de {mention(next_manager_id)}."
    wait_note = (
        f"\n⏱️ Ha tardado {_format_wait(waited_seconds)}."
        if waited_seconds is not None
        else ""
    )
    message = (
        f"✅ <b>{manager_name}</b> ficha a <b>{row['name']}</b> ({row['team']}) "
        f"por {_eur(price)}{sim_note}.{wait_note}\n"
        f"Le quedan {_eur(remaining)}. {turn_note}"
    )

    return {
        "status": "applied",
        "message": message,
        "player": {
            "player_id": player_id,
            "name": row["name"],
            "team": row["team"],
            "price": price,
        },
        "remaining": remaining,
        "next_manager": next_manager,
    }


def _apply_confirmed_pick(manager_id: int, player_id: int, players_by_id: dict) -> dict:
    if player_id not in players_by_id:
        return _rejected(
            draft.DraftError.PLAYER_UNKNOWN.name,
            "No encuentro a ese jugador en el mercado del draft.",
        )

    reservation = _reserve_pick(manager_id, player_id, players_by_id)
    outcome = reservation["outcome"]

    if outcome == "invalid":
        message = reservation["message"]
        # The pure engine names the manager on turn but knows nothing about
        # Telegram; the whole point of this rejection is to wake that person
        # up, so upgrade the name to a mention here.
        if reservation["error"] == draft.DraftError.NOT_YOUR_TURN.name:
            turn = draft.whose_turn(load_state())
            if turn is not None:
                message = f"⛔ No es tu turno — le toca a {mention(turn)}."
        return _rejected(reservation["error"], message)
    if outcome == "duplicate":
        return _duplicate_pick_response(reservation["pick"])

    pick_doc = reservation["pick"]
    doc_id = _pick_doc_id(pick_doc["round"], pick_doc["position"])
    price = pick_doc["price"]

    applied_to_biwenger = False
    if config.DRAFT_APPLY_TO_BIWENGER:
        try:
            # Touch the session only now: the slot is reserved and the transfer
            # is certain, so a rejected or duplicate pick never authenticates.
            _with_session(
                lambda client: client.transfer_player(
                    player_id=player_id,
                    manager_id=manager_id,
                    amount=price,
                )
            )
            applied_to_biwenger = True
        except Exception:
            logger.exception(
                "Biwenger transfer failed for a draft pick.", extra={"pick": doc_id}
            )
            landed = _transfer_landed(manager_id, player_id)
            if landed is True:
                # The transfer went through and only the response was lost.
                # Finalising is the honest record; retrying would buy twice.
                logger.info(
                    "Lost response, but Biwenger has the player — finalising.",
                    extra={"pick": doc_id},
                )
                applied_to_biwenger = True
            else:
                store.fs.set_document(
                    _picks_path(config.DRAFT_SEASON),
                    doc_id,
                    {
                        "status": (
                            PICK_STATUS_REVERTED
                            if landed is False
                            else PICK_STATUS_RESERVED
                        )
                    },
                    merge=True,
                )
                return _rejected(
                    ERROR_BIWENGER_TRANSFER_FAILED,
                    (
                        "❌ Biwenger no aceptó el fichaje y no se ha aplicado nada. "
                        "Vuelve a intentarlo en un minuto."
                        if landed is False
                        else "⚠️ Se perdió la conexión con Biwenger y no he podido "
                        "comprobar si el fichaje entró. La plaza queda bloqueada "
                        "a propósito: avisa al admin, reintentar podría ficharlo "
                        "dos veces."
                    ),
                )

    new_state, waited = _finalize_pick(manager_id, player_id, players_by_id)
    store.fs.set_document(
        _picks_path(config.DRAFT_SEASON),
        doc_id,
        {
            "status": PICK_STATUS_APPLIED,
            "applied_to_biwenger": applied_to_biwenger,
            "applied_at": time.time(),
            "waited_seconds": waited,
        },
        merge=True,
    )

    return _applied_response(
        new_state,
        manager_id,
        player_id,
        players_by_id,
        price,
        applied_to_biwenger,
        waited,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def submit_pick(telegram_user_id: str, query: str) -> dict:
    """Resolve free-text `query` against the market and apply the pick."""
    closed = _reject_if_closed()
    if closed is not None:
        return closed
    manager = _get_registered_manager(telegram_user_id)
    if manager is None:
        return _rejected(
            ERROR_NOT_REGISTERED,
            "No estás registrado en el draft. Regístrate primero con tu nombre.",
        )

    players_by_id = _load_market()
    rows = list(players_by_id.values())

    match = draft.resolve_player_name(query, rows)
    if not match.ok:
        if not match.candidates:
            return _rejected(
                draft.DraftError.PLAYER_UNKNOWN.name,
                "No encuentro a ese jugador en el mercado del draft.",
            )
        return {
            "status": "ambiguous",
            "candidates": [
                {
                    "player_id": row["player_id"],
                    "name": row["name"],
                    "team": row["team"],
                    "price": row["price"],
                }
                for row in match.candidates
            ],
            "message": "Hay varios jugadores que encajan con eso, elige uno:",
        }

    return _apply_confirmed_pick(
        manager["manager_id"], match.row["player_id"], players_by_id
    )


def confirm_pick(telegram_user_id: str, player_id: int) -> dict:
    """Apply a pick the user already disambiguated (tapped a candidate)."""
    closed = _reject_if_closed()
    if closed is not None:
        return closed
    manager = _get_registered_manager(telegram_user_id)
    if manager is None:
        return _rejected(
            ERROR_NOT_REGISTERED,
            "No estás registrado en el draft. Regístrate primero con tu nombre.",
        )

    players_by_id = _load_market()
    return _apply_confirmed_pick(manager["manager_id"], player_id, players_by_id)


def undo_last_pick(telegram_user_id: str) -> dict:
    """Revert the most recent pick. Restricted to `config.DRAFT_ADMIN_TELEGRAM_ID`."""
    closed = _reject_if_closed()
    if closed is not None:
        return closed
    admin_id = config.DRAFT_ADMIN_TELEGRAM_ID
    if not admin_id or str(telegram_user_id) != str(admin_id):
        return {
            "status": "rejected",
            "message": "Solo el admin del draft puede deshacer un fichaje.",
        }

    state = load_state()
    if not state.picks:
        return {"status": "rejected", "message": "No hay ningún fichaje que deshacer."}

    last_pick = state.picks[-1]
    doc_id = _pick_doc_id(last_pick.round, last_pick.position)
    pick_doc = store.fs.get_document(_picks_path(config.DRAFT_SEASON), doc_id)
    manager_name = LEAGUE_MEMBERS.get(last_pick.manager_id, str(last_pick.manager_id))
    player_name = (pick_doc or {}).get("player_name") or last_pick.player_id

    if pick_doc is not None and pick_doc.get("applied_to_biwenger"):
        # Two calls instead of `revertOffer`: Biwenger hands out no id for an
        # admin transfer, so the release and the refund are driven separately.
        # The release goes first — a player left unowned is obvious on the
        # board, whereas a refund without a release would silently pay twice.
        try:
            _with_session(
                lambda client: client.release_player(player_id=last_pick.player_id)
            )
            _with_session(
                lambda client: client.apply_bonus(
                    amounts={
                        m: (last_pick.price if m == last_pick.manager_id else 0)
                        for m in LEAGUE_MEMBERS
                    },
                    reason=f"Draft: deshecho el fichaje de {player_name}",
                )
            )
        except Exception:
            logger.exception(
                "Failed to revert the Biwenger transfer for a draft undo.",
                extra={"pick": doc_id},
            )
            return {
                "status": "rejected",
                "message": (
                    f"Biwenger rechazó deshacer el fichaje de {manager_name}. "
                    "Deshazlo a mano en el panel de admin."
                ),
            }

    new_squads = {m: list(v) for m, v in state.squads.items()}
    new_squads[last_pick.manager_id] = new_squads[last_pick.manager_id][:-1]
    new_spent = dict(state.spent)
    new_spent[last_pick.manager_id] = (
        new_spent.get(last_pick.manager_id, 0) - last_pick.price
    )
    new_state = draft.DraftState(
        order=list(state.order),
        budgets=dict(state.budgets),
        picks=list(state.picks[:-1]),
        squads=new_squads,
        spent=new_spent,
    )
    # The clock restarts: an undo is an admin action, and the manager should
    # not be charged for however long it took someone to notice.
    _save_state(new_state, turn_started_at=time.time())
    store.fs.set_document(
        _picks_path(config.DRAFT_SEASON),
        doc_id,
        {"status": PICK_STATUS_REVERTED},
        merge=True,
    )

    return {
        "status": "reverted",
        "message": (
            f"↩️ Fichaje de <b>{manager_name}</b> ({player_name}) deshecho. "
            f"Le toca de nuevo a {mention(last_pick.manager_id)}."
        ),
    }


def export_picks() -> dict:
    """Every applied pick, in draft order — for the season's audit trail."""
    docs = store.fs.query(_picks_path(config.DRAFT_SEASON), order_by="global_pick")
    picks = [
        {
            "round": d.get("round"),
            "position": d.get("position"),
            "global_pick": d.get("global_pick"),
            "manager_id": d.get("manager_id"),
            "manager_name": d.get("manager_name"),
            "player_id": d.get("player_id"),
            "player_name": d.get("player_name"),
            "player_team": d.get("player_team"),
            "price": d.get("price"),
            "status": d.get("status"),
        }
        for d in docs
        if d.get("status") == PICK_STATUS_APPLIED
    ]
    if not picks:
        return {
            "message": "Todavía no hay fichajes confirmados en el draft.",
            "messages": [],
            "picks": [],
        }

    state = load_state()
    by_manager: dict = {}
    for p in picks:
        by_manager.setdefault(p["manager_id"], []).append(p)

    # One message per manager: 15 picks x 7 managers overflows Telegram's
    # 4096-char limit as a single block, and a squad is what the reader wants
    # to see whole anyway.
    messages = []
    for manager_id in state.order:
        squad = by_manager.get(manager_id)
        if not squad:
            continue
        spent = sum(p["price"] or 0 for p in squad)
        left = state.budgets.get(manager_id, 0) - spent
        waits = [p["waited_seconds"] for p in squad if p.get("waited_seconds")]
        # Median, not mean: a draft spans nights, and one turn that landed at
        # 3am would otherwise decide the whole ranking.
        pace = (
            f" · ⏱️ {_format_wait(sorted(waits)[len(waits) // 2])} de mediana"
            if waits
            else ""
        )
        lines = [
            f"<b>{squad[0]['manager_name']}</b> — {len(squad)} jugadores · "
            f"{_eur(spent)} gastados · {_eur(left)} libres{pace}"
        ]
        lines += [
            f"{p['global_pick']:>3}. {p['player_name']} "
            f"({p['player_team']}) {_eur(p['price'] or 0)}"
            for p in squad
        ]
        messages.append("\n".join(lines))

    return {
        "message": f"🏁 <b>Draft {config.DRAFT_SEASON}</b> — {len(picks)} fichajes",
        "messages": messages,
        "picks": picks,
    }
