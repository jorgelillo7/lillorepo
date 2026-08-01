"""Persistence + orchestration for the annual snake draft — `/draft/*`.

Wraps the pure engine in `logic/draft.py` with:

- Firestore persistence of manager registration, the serialised
  `DraftState`, and a per-pick idempotency guard.
- The Biwenger `transfer_player`/`release_player`/`apply_bonus` calls that
  actually move a player and charge or refund a manager.
- Free-text name -> market player resolution for the Telegram pick flow.

Every public function returns a plain dict with a `message` field — a
ready-to-send Spanish string — because the bot layer holds no business
logic of its own.

Firestore layout (collection paths, see `core/sdk/firestore.py`):
    draft/{season}/managers  -- doc id = telegram_user_id (string)
    draft/{season}/picks     -- doc id = "R{round:02d}P{position:02d}"
    draft/{season}/state     -- single doc, id `STATE_DOC_ID`

`DRAFT_APPLY_TO_BIWENGER` gates the Biwenger *writes* only: reading the
cf-base player database to resolve the canonical Biwenger id happens either
way — it is side-effect-free, and the same real ids are needed whether or not
the gate is later flipped on.

Undo is a `release_player` + `apply_bonus` pair rather than `revertOffer`:
Biwenger issues no identifier for an admin transfer (the POST answers 204 with
an empty body and no headers, and the `adminTransfer` board entries carry no
`id`), so there is nothing to revert *by*.

Idempotency: a pick is only ever written through the deterministic
`R{round}P{position}` doc id. `_reserve_pick` creates that doc inside a
Firestore transaction, failing (returning "duplicate") if it already
exists — this is what makes retried Telegram webhooks and duplicate bot
taps safe. The Biwenger transfer call itself happens *after* the
transaction commits, never inside it (a transaction body can be re-run by
Firestore on contention, and Biwenger's transfer endpoint has no
idempotency key of its own).
"""

from typing import Optional

import requests

from core.constants import LEAGUE_MEMBERS
from core.sdk import firestore as fs
from core.sdk.biwenger import BiwengerClient
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from packages.biwenger_tools.api.logic.orchestration import build_biwenger_session
from packages.biwenger_tools.api.logic.player_matching import normalize_name

logger = get_logger(__name__)

STATE_DOC_ID = "current"

PICK_STATUS_RESERVED = "reserved"
PICK_STATUS_APPLIED = "applied"
PICK_STATUS_REVERTED = "reverted"

# Service-level rejections outside `draft.DraftError` — the pure engine
# only knows about pick legality; registration/authorization live here.
ERROR_NOT_REGISTERED = "NOT_REGISTERED"
ERROR_PICK_IN_PROGRESS = "PICK_IN_PROGRESS"
ERROR_BIWENGER_TRANSFER_FAILED = "BIWENGER_TRANSFER_FAILED"


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


# ---------------------------------------------------------------------------
# Manager registration
# ---------------------------------------------------------------------------


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
        for _, data in fs.list_documents(_managers_path(config.DRAFT_SEASON))
        if data.get("manager_id") is not None
    }
    managers = [
        {
            "manager_id": mid,
            "name": LEAGUE_MEMBERS.get(mid, str(mid)),
            "claimed_by": claimed.get(mid, ""),
        }
        for mid in _load_state().order
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
        manager_id = int(manager_id) if int(manager_id) in _load_state().order else None
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
            for _, data in fs.list_documents(_managers_path(config.DRAFT_SEASON))
            if int(data.get("manager_id") or 0) == manager_id
            and str(data.get("telegram_user_id")) != str(telegram_user_id)
        ),
        "",
    )
    manager_name = LEAGUE_MEMBERS[manager_id]
    fs.set_document(
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
    return fs.get_document(_managers_path(config.DRAFT_SEASON), str(telegram_user_id))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def _load_state() -> draft.DraftState:
    data = fs.get_document(_state_path(config.DRAFT_SEASON), STATE_DOC_ID)
    return draft.new_draft_state() if data is None else draft.state_from_dict(data)


def _save_state(state: draft.DraftState) -> None:
    fs.set_document(
        _state_path(config.DRAFT_SEASON), STATE_DOC_ID, draft.state_to_dict(state)
    )


def _mention(manager_id: int) -> str:
    """HTML mention of the manager's registered Telegram user.

    A `tg://user?id=` link makes Telegram actually notify the person on
    turn, username or not. Falls back to the plain name when the manager
    has not done `/soy` yet — a dead link would notify nobody anyway.
    """
    name = LEAGUE_MEMBERS.get(manager_id, str(manager_id))
    for _, data in fs.list_documents(_managers_path(config.DRAFT_SEASON)):
        if int(data.get("manager_id") or 0) == manager_id:
            return f'<a href="tg://user?id={data["telegram_user_id"]}">{name}</a>'
    return name


def get_state() -> dict:
    """Current turn + per-manager budgets/spend/squad size, name-keyed."""
    state = _load_state()
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
            f"🎯 Le toca a {_mention(turn)}",
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


# ---------------------------------------------------------------------------
# Frozen market
# ---------------------------------------------------------------------------


_MARKET_CACHE: dict | None = None


def reset_market_cache() -> None:
    """Drop the cached market so the next call re-reads it."""
    global _MARKET_CACHE
    _MARKET_CACHE = None


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


# ---------------------------------------------------------------------------
# Pick reservation (the idempotency guard)
# ---------------------------------------------------------------------------


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
        client = fs.get_client()
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

    return fs.run_transaction(txn)


def _finalize_pick(
    manager_id: int, player_id: int, players_by_id: dict
) -> draft.DraftState:
    """Apply the (already-reserved, already-validated) pick to `DraftState`."""

    def txn(transaction):
        client = fs.get_client()
        state_ref = client.collection(_state_path(config.DRAFT_SEASON)).document(
            STATE_DOC_ID
        )
        state_snapshot = state_ref.get(transaction=transaction)
        state = (
            draft.state_from_dict(state_snapshot.to_dict())
            if state_snapshot.exists
            else draft.new_draft_state()
        )
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
            return state
        transaction.set(state_ref, draft.state_to_dict(new_state))
        return new_state

    return fs.run_transaction(txn)


def _duplicate_pick_response(pick_doc: dict) -> dict:
    manager_name = pick_doc.get("manager_name") or str(pick_doc.get("manager_id"))
    player_name = pick_doc.get("player_name") or pick_doc.get("player_id")

    if pick_doc.get("status") == PICK_STATUS_APPLIED:
        state = _load_state()
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
    turn_note = (
        f"🎯 Turno de {_mention(next_manager_id)}."
        if next_manager_id is not None
        else "🏁 ¡Draft completado!"
    )
    message = (
        f"✅ <b>{manager_name}</b> ficha a <b>{row['name']}</b> ({row['team']}) "
        f"por {_eur(price)}{sim_note}. Le quedan {_eur(remaining)}. {turn_note}"
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
            turn = draft.whose_turn(_load_state())
            if turn is not None:
                message = f"⛔ No es tu turno — le toca a {_mention(turn)}."
        return _rejected(reservation["error"], message)
    if outcome == "duplicate":
        return _duplicate_pick_response(reservation["pick"])

    pick_doc = reservation["pick"]
    doc_id = _pick_doc_id(pick_doc["round"], pick_doc["position"])
    price = pick_doc["price"]

    applied_to_biwenger = False
    if config.DRAFT_APPLY_TO_BIWENGER:
        try:
            # Authenticate only now: the slot is reserved and the transfer is
            # certain, so a rejected or duplicate pick never logs in.
            biwenger = build_biwenger_session()
            biwenger.transfer_player(
                player_id=player_id,
                manager_id=manager_id,
                amount=price,
            )
            applied_to_biwenger = True
        except Exception:
            logger.exception(
                "Biwenger transfer failed for a draft pick.", extra={"pick": doc_id}
            )
            fs.set_document(
                _picks_path(config.DRAFT_SEASON),
                doc_id,
                {"status": PICK_STATUS_RESERVED},
                merge=True,
            )
            return _rejected(
                ERROR_BIWENGER_TRANSFER_FAILED,
                "Biwenger rechazó el fichaje. La plaza sigue reservada — reintenta "
                "más tarde o avisa al admin, no se ha aplicado ningún cambio.",
            )

    new_state = _finalize_pick(manager_id, player_id, players_by_id)
    fs.set_document(
        _picks_path(config.DRAFT_SEASON),
        doc_id,
        {
            "status": PICK_STATUS_APPLIED,
            "applied_to_biwenger": applied_to_biwenger,
        },
        merge=True,
    )

    return _applied_response(
        new_state, manager_id, player_id, players_by_id, price, applied_to_biwenger
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def submit_pick(telegram_user_id: str, query: str) -> dict:
    """Resolve free-text `query` against the market and apply the pick."""
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
    admin_id = config.DRAFT_ADMIN_TELEGRAM_ID
    if not admin_id or str(telegram_user_id) != str(admin_id):
        return {
            "status": "rejected",
            "message": "Solo el admin del draft puede deshacer un fichaje.",
        }

    state = _load_state()
    if not state.picks:
        return {"status": "rejected", "message": "No hay ningún fichaje que deshacer."}

    last_pick = state.picks[-1]
    doc_id = _pick_doc_id(last_pick.round, last_pick.position)
    pick_doc = fs.get_document(_picks_path(config.DRAFT_SEASON), doc_id)
    manager_name = LEAGUE_MEMBERS.get(last_pick.manager_id, str(last_pick.manager_id))
    player_name = (pick_doc or {}).get("player_name") or last_pick.player_id

    if pick_doc is not None and pick_doc.get("applied_to_biwenger"):
        # Two calls instead of `revertOffer`: Biwenger hands out no id for an
        # admin transfer, so the release and the refund are driven separately.
        # The release goes first — a player left unowned is obvious on the
        # board, whereas a refund without a release would silently pay twice.
        try:
            biwenger = build_biwenger_session()
            biwenger.release_player(player_id=last_pick.player_id)
            biwenger.apply_bonus(
                amounts={
                    m: (last_pick.price if m == last_pick.manager_id else 0)
                    for m in LEAGUE_MEMBERS
                },
                reason=f"Draft: deshecho el fichaje de {player_name}",
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
    _save_state(new_state)
    fs.set_document(
        _picks_path(config.DRAFT_SEASON),
        doc_id,
        {"status": PICK_STATUS_REVERTED},
        merge=True,
    )

    return {
        "status": "reverted",
        "message": (
            f"↩️ Fichaje de <b>{manager_name}</b> ({player_name}) deshecho. "
            f"Le toca de nuevo a {_mention(last_pick.manager_id)}."
        ),
    }


def _eur(amount: int) -> str:
    """Euros as millions, the unit the league actually talks in."""
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")


def export_picks() -> dict:
    """Every applied pick, in draft order — for the season's audit trail."""
    docs = fs.query(_picks_path(config.DRAFT_SEASON), order_by="global_pick")
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

    state = _load_state()
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
        lines = [
            f"<b>{squad[0]['manager_name']}</b> — {len(squad)} jugadores · "
            f"{_eur(spent)} gastados · {_eur(left)} libres"
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
