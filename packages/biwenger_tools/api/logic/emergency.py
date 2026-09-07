"""Emergency clausulazo — `POST /emergency/clausulazo/{preview,execute}`.

Two-phase flow:

1. **Preview** — read recent losses + cash, decide which position to
   reinforce, and post a confirmation message. When the losses don't
   uniquely identify a position (>1 loss in the last 24h, or 1
   multi-position loss), the preview posts a *selector* message and
   the user picks a position; the bot's tap re-enters this function
   via `force_position` / `force_weakest`, which goes straight to the
   confirmation message.

2. **Execute** — fired by the bot when the user taps "Sí". POSTs the
   clausulazo with the exact `player_id`/`owner_user_id`/`amount` the
   user approved and notifies the result.

When the squad cannot field a legal eleven at all (`composition_ok` is
False), the preview forks into rebuild mode instead: a multi-signing plan
built by `rebuild.build_plan`, stored via `rebuild_store` and
confirmed/executed as a whole via `_preview_rebuild`/`execute_rebuild`.

Hard rules:

- Cash is **justo** — `target = cash` (no dynamic margin, unlike
  `/recomendar`). The op must never push the user into the red.
- `amount = clause_value` exactly — minimum valid clausulazo, no
  inflation.
- Detection lives in `clausulazo_detection.py`; rival candidate
  selection in `clausulazo_candidates.py`. This module is just the
  flow + UX.
"""

import html
import time
from typing import Optional

from core.sdk.telegram import send_telegram_message_or_raise
from core.utils import format_euros, get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.clausulazo_candidates import (
    filter_affordable,
    gather_rivals,
    pick_top_in_position,
    sf_of,
)
from packages.biwenger_tools.api.logic.clausulazo_detection import (
    OUTFIELD_POSITION_IDS,
    recent_lost_players,
    unique_outfield_positions,
    weakest_outfield_position,
)
from packages.biwenger_tools.api.logic import rebuild, rebuild_store
from packages.biwenger_tools.api.logic.draft import composition_ok
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID, xi_snapshot
from packages.biwenger_tools.api.logic.orchestration import (
    build_biwenger_session,
    build_context,
    require_telegram,
)
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import POSITION_SHORT

logger = get_logger(__name__)

_POSITION_LABELS_ES = {1: "Portero", 2: "Defensa", 3: "Centrocampista", 4: "Delantero"}


# --- Keyboards -----------------------------------------------------------


def _confirmation_keyboard(player_id: int, owner_id: int, amount: int) -> dict:
    """Inline keyboard with Sí/No.

    `callback_data` is capped at 64 bytes by Telegram. The packed
    `e:c:<player>:<owner>:<amount>` payload is ~30 chars on real
    numbers (player/owner ids are 6 digits, amount up to 9 digits).
    """
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Sí, clausular",
                    "callback_data": f"e:c:{player_id}:{owner_id}:{amount}",
                },
                {"text": "❌ No, cancelar", "callback_data": "e:n"},
            ]
        ]
    }


def _selector_keyboard(positions: list[int]) -> dict:
    """One button per outfield position in `positions`, plus weakest-line.

    `e:p:<pid>` taps trigger a refined preview locked to that position;
    `e:m` triggers the weakest-line fallback (so the user can override
    the auto-detected positions when they prefer to plug a different
    gap). `e:n` cancels the flow.
    """
    rows = [
        [
            {
                "text": f"✅ Reforzar {_POSITION_LABELS_ES[pos]}",
                "callback_data": f"e:p:{pos}",
            }
        ]
        for pos in positions
    ]
    rows.append([{"text": "🌍 Línea más mermada", "callback_data": "e:m"}])
    rows.append([{"text": "❌ Cancelar", "callback_data": "e:n"}])
    return {"inline_keyboard": rows}


def _rebuild_keyboard(plan_id: str) -> dict:
    """Confirm the whole plan. The payload is a plan id and nothing else —
    `callback_data` is capped at 64 bytes and a seven-signing basket does
    not fit in it. Execution reads the stored plan rather than a freshly
    recomputed one, but it is not a promise that what runs is unchanged:
    the market has kept moving since the preview, so `execute_rebuild`
    re-verifies every signing against it before spending a euro.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Sí, reconstruir", "callback_data": f"e:r:{plan_id}"},
                {"text": "❌ No, cancelar", "callback_data": "e:n"},
            ]
        ]
    }


# --- Message formatters --------------------------------------------------


def _format_selector_text(losses: list[dict], cash: int) -> str:
    """Render the multi-loss selector message.

    Lists every recent loss with its position(s) so the user can see
    what happened, then asks which line to reinforce. Multi-position
    players show both positions (e.g. `DEF/MED`).
    """
    lines = [
        "🚨 <b>Emergencia — varias pérdidas recientes</b>",
        "",
        f"Tu cash: <b>{format_euros(cash)}</b>",
        "",
        "Te han clausulado (últimas 24h):",
    ]
    for loss in losses:
        primary = POSITION_SHORT.get(loss["position_id"], "?")
        alts = [POSITION_SHORT.get(p, "?") for p in loss["alt_positions"]]
        pos_str = "/".join([primary, *alts]) if alts else primary
        lines.append(f"  · <b>{_escape(loss['name'])}</b> ({pos_str})")
    lines.append("")
    lines.append("<i>¿Qué línea quieres reforzar?</i>")
    return "\n".join(lines)


def _format_goalkeeper_losses_text(losses: list[dict], cash: int) -> str:
    """Render the report for a batch of losses that were all goalkeepers.

    Biwenger allows a manager's last goalkeeper to be claused; the league does
    not, and the admin cancels the operation and penalises whoever tried. So
    nobody is ever left without one, one is all a legal eleven needs, and there
    is no goalkeeper line to offer — but the losses themselves are real and
    must be named, not folded into "no losses".
    """
    lines = [
        "🚨 <b>Emergencia — clausulazo(s) recientes en portería</b>",
        "",
        f"Tu cash: <b>{format_euros(cash)}</b>",
        "",
        "Te han clausulado (últimas 24h):",
    ]
    for loss in losses:
        lines.append(f"  · <b>{_escape(loss['name'])}</b> (POR)")
    lines.append("")
    lines.append(
        "<i>No hay línea de portero que reforzar por esta vía — con un solo "
        "portero el once es legal, y al último no te lo pueden quitar: el "
        "admin cancela el clausulazo y penaliza.</i>"
    )
    return "\n".join(lines)


def _format_preview_text(
    target: dict,
    reason: str,
    fallback_note: str,
    cash: int,
) -> str:
    pos_short = POSITION_SHORT.get(target["position_id"], "?")
    extra = f" — {fallback_note}" if fallback_note else ""
    return (
        f"🚨 <b>Emergencia — confirma el clausulazo</b>\n"
        f"\n"
        f"Motivo: <i>{reason}{extra}</i>\n"
        f"\n"
        f"Objetivo: <b>{target['name']}</b> ({pos_short}) "
        f"de <b>{target['owner']}</b>\n"
        f"Cláusula: <b>{format_euros(target['clause_value'])}</b> · "
        f"SF {sf_of(target)}\n"
        f"Tu cash: <b>{format_euros(cash)}</b>\n"
        f"\n"
        f"<i>Esta operación es irreversible.</i>"
    )


def _format_no_target_text(reason: str, cash: int) -> str:
    return (
        f"🚨 <b>Emergencia</b>\n"
        f"\n"
        f"Sin candidatos asequibles. Tu cash: <b>{format_euros(cash)}</b>. "
        f"Motivo: <i>{reason}</i>."
    )


def _format_executed_text(amount: int, player_name: str, cash_after: int) -> str:
    return (
        f"🚨 <b>Clausulazo ejecutado</b>\n"
        f"\n"
        f"Pagado <b>{format_euros(amount)}</b> por "
        f"<b>{_escape(player_name)}</b>.\n"
        f"Cash restante: <b>{format_euros(cash_after)}</b>"
    )


def _format_rebuild_text(
    plan, eleven: Optional[dict], projected: list[dict], cash: int
) -> str:
    """Render the rebuild plan preview: every signing, the eleven it would
    field, and whether the money reaches a legal one — before a euro moves.
    """
    lines = [
        "🚨 <b>Emergencia — hace falta reconstruir</b>",
        "",
        f"Tu cash: <b>{format_euros(cash)}</b>",
        f"Formación objetivo: <b>{plan.formation}</b>",
        "",
    ]
    if plan.signings:
        lines.append("Fichajes propuestos:")
        for signing in plan.signings:
            pos = POSITION_SHORT.get(signing.line, "?")
            lines.append(
                f"  · <b>{_escape(signing.row['name'])}</b> ({pos}) de "
                f"<b>{signing.row['owner']}</b> — "
                f"{format_euros(signing.row['clause_value'])}"
            )
        lines.append("")
        lines.append(f"Coste total: <b>{format_euros(plan.total_cost)}</b>")
        if plan.spends_floor:
            lines.append("<i>Hace falta gastar el colchón de seguridad.</i>")
    else:
        lines.append("<i>No hay fichajes asequibles con el cash disponible.</i>")

    lines.append("")
    if eleven is None:
        lines.append("<i>Ni siquiera con este plan se puede formar un once legal.</i>")
    else:
        by_id = {row["bw_id"]: row for row in projected}
        starters = [by_id[bid] for bid in eleven["starter_ids"] if bid in by_id]
        names = ", ".join(sorted(row["name"] for row in starters))
        lines.append(f"Once resultante (SF {eleven['total_sf']}): {names}")

    if not plan.completes_xi:
        lines.append("")
        lines.append(
            "<i>El cash no llega para completar un once legal — quedará al "
            "menos un hueco sin cubrir.</i>"
        )

    lines.append("")
    lines.append("<i>Esta operación es irreversible.</i>")
    return "\n".join(lines)


def _format_rebuild_missing_text() -> str:
    return (
        "🚨 <b>Emergencia</b>\n\n"
        "Este plan ya no está disponible (ya se ejecutó o caducó)."
    )


def _format_rebuild_expired_text() -> str:
    return (
        "🚨 <b>Emergencia</b>\n\n"
        "El plan ha caducado — las cláusulas se mueven y ya no puede "
        "ejecutarse. Repite <code>/emergencia</code>."
    )


def _format_rebuild_not_needed_text() -> str:
    return (
        "🚨 <b>Emergencia</b>\n\n"
        "La plantilla ya puede formar un once legal — no se compra nada."
    )


def _format_rebuild_signing_text(outcome: dict) -> str:
    """One signing's outcome, sent the moment it happens.

    Batching this until the whole plan finished used to mean a request that
    outlives gunicorn's timeout is SIGKILLed with no `except` running, and
    every purchase already made vanishes from the chat along with it.
    """
    pos = POSITION_SHORT.get(outcome["line"], "?")
    status = outcome["status"]
    if status == "bought":
        swap_note = " (sustituto)" if outcome.get("swapped") else ""
        return (
            f"🚨 <b>Reconstrucción</b> — ✅ ({pos}){swap_note} "
            f"<b>{_escape(outcome['name'])}</b> — "
            f"{format_euros(outcome['amount'])}"
        )
    if status == "unknown":
        return (
            f"🚨 <b>Reconstrucción</b> — ⚠️ ({pos}) resultado desconocido — "
            f"<code>{_escape(outcome.get('error', ''))}</code>. Se detiene el "
            "resto del plan: comprueba tu plantilla y tu cash antes de repetir."
        )
    if status == "skipped":
        return (
            f"🚨 <b>Reconstrucción</b> — ⏭️ ({pos}) ese hueco ya no existe, "
            "no se compra."
        )
    if status == "unavailable":
        return (
            f"🚨 <b>Reconstrucción</b> — ⏭️ ({pos}) el sustituto ya no está "
            "disponible, no se compra."
        )
    return f"🚨 <b>Reconstrucción</b> — ❌ ({pos}) sin cubrir — nadie asequible."


def _format_rebuild_summary_text(
    outcomes: list[dict], cash_after: int, fields_xi: bool
) -> str:
    bought = sum(1 for outcome in outcomes if outcome["status"] == "bought")
    xi_line = (
        "<i>La plantilla ya puede formar un once legal.</i>"
        if fields_xi
        else "<i>La plantilla TODAVÍA NO puede formar un once legal.</i>"
    )
    lines = [
        "🚨 <b>Reconstrucción — resumen</b>",
        "",
        f"Fichajes realizados: <b>{bought}</b> de <b>{len(outcomes)}</b>.",
        f"Cash restante: <b>{format_euros(cash_after)}</b>",
        "",
        xi_line,
    ]
    return "\n".join(lines)


# --- Reason strings ------------------------------------------------------


def _reason_force_weakest() -> str:
    return "refuerza la línea más mermada (elegido)"


def _reason_force_position(position_id: int) -> str:
    return (
        f"refuerza la línea de "
        f"{_POSITION_LABELS_ES[position_id].lower()}s (elegido)"
    )


def _reason_single_loss(loss: dict) -> str:
    return (
        f"acaban de clausularte un "
        f"{_POSITION_LABELS_ES[loss['position_id']].lower()} "
        f"({loss['name']}) en las últimas 24h — refuerza esa línea"
    )


def _reason_no_losses() -> str:
    return "sin clausulazos recientes contra ti — refuerza la línea más mermada"


def _reason_goalkeeper_loss(loss: dict) -> str:
    return (
        f"te han clausulado a tu portero ({loss['name']}) — esa línea no se "
        "puede reforzar, refuerza la más mermada"
    )


def _fallback_note(preferred_position: int, in_preferred: bool) -> str:
    if in_preferred:
        return ""
    return (
        f"sin candidatos en {_POSITION_LABELS_ES[preferred_position]}, "
        "voy al mejor SF disponible"
    )


# --- Flow ----------------------------------------------------------------


def preview_clausulazo(
    force_position: Optional[int] = None, force_weakest: bool = False
) -> dict:
    """Compute the target + reason and post the corresponding message.

    Cases:
    - 0 losses (and no force) → reinforce weakest outfield line.
    - 1 single-position loss (and no force) → target that position.
    - Otherwise (multi-loss, multi-pos loss) → post a selector with one
      button per affected outfield position + weakest-line fallback.
      The user's tap re-enters with `force_position` / `force_weakest`.

    Returns a diagnostics dict; the user-visible artefact is the
    Telegram message.
    """
    ctx = build_context()
    biwenger = ctx.biwenger

    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_ids = {p.get("id") for p in my_squad if p.get("id") is not None}
    cash = int(biwenger.get_account_state(my_squad, ctx.biwenger_players)["cash"])

    league_users = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    my_manager_name = league_users.get(int(biwenger.user_id), "")

    losses = recent_lost_players(
        biwenger, ctx.biwenger_players, my_manager_name, now_epoch=time.time()
    )

    my_rows = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    if not composition_ok(rebuild.eligibilities(my_rows)):
        # Structural, not circumstantial: this asks whether the players exist,
        # never whether they are fit. Rebuild outranks every other path,
        # including a forced position — a selector is meaningless when no
        # single signing can restore an eleven.
        return _preview_rebuild(ctx, my_rows, my_ids, cash, losses)

    preferred_position, reason, selector_payload = _resolve_intent(
        losses=losses,
        my_squad=my_squad,
        biwenger_players=ctx.biwenger_players,
        cash=cash,
        force_position=force_position,
        force_weakest=force_weakest,
    )
    if selector_payload is not None:
        return selector_payload

    rivals = gather_rivals(biwenger, ctx.biwenger_players, ctx.jp_index)
    affordable = filter_affordable(rivals, my_ids, target=cash)
    target, in_preferred = pick_top_in_position(affordable, preferred_position)

    payload = {
        "cash": cash,
        "preferred_position": preferred_position,
        "losses": losses,
    }

    if target is None:
        _send(_format_no_target_text(reason, cash))
        return {**payload, "target": None, "reason": reason}

    text = _format_preview_text(
        target, reason, _fallback_note(preferred_position, in_preferred), cash
    )
    _send(
        text,
        reply_markup=_confirmation_keyboard(
            player_id=int(target["bw_id"]),
            owner_id=int(target["owner_user_id"]),
            amount=int(target["clause_value"]),
        ),
    )
    return {
        **payload,
        "reason": reason,
        "target": {
            "player_id": target["bw_id"],
            "owner_user_id": target["owner_user_id"],
            "owner": target["owner"],
            "name": target["name"],
            "position_id": target["position_id"],
            "amount": target["clause_value"],
            "sf": sf_of(target),
        },
    }


def _preview_rebuild(
    ctx, my_rows: list[dict], my_ids: set, cash: int, losses: list[dict]
) -> dict:
    """Build, prove, store and offer a rebuild plan. Never buys anything.

    Entered instead of the single-signing flow when `composition_ok` says
    the squad cannot field a legal eleven at all — see `preview_clausulazo`.
    """
    rivals = gather_rivals(ctx.biwenger, ctx.biwenger_players, ctx.jp_index)
    affordable = filter_affordable(rivals, my_ids, target=cash)
    plan = rebuild.build_plan(my_rows=my_rows, affordable=affordable, cash=cash)

    # Prove it: the eleven is computed from the squad the plan would leave,
    # never asserted. `xi_snapshot` has no side effects, unlike `pick_lineup`.
    projected = my_rows + [signing.row for signing in plan.signings]
    eleven = xi_snapshot(projected)

    plan_id = rebuild_store.store(plan)
    _send(
        _format_rebuild_text(plan, eleven, projected, cash),
        reply_markup=_rebuild_keyboard(plan_id) if plan.signings else None,
    )
    return {
        "cash": cash,
        "losses": losses,
        "rebuild": True,
        "plan_id": plan_id,
        "formation": plan.formation,
        "total_cost": plan.total_cost,
        "completes_xi": plan.completes_xi,
    }


def _resolve_intent(
    *,
    losses: list[dict],
    my_squad: list,
    biwenger_players: dict,
    cash: int,
    force_position: Optional[int],
    force_weakest: bool,
) -> tuple[int, str, Optional[dict]]:
    """Decide `(preferred_position, reason, selector_payload)`.

    When `selector_payload` is not None, the caller should post the
    selector and return that payload as-is — there is no target yet,
    the user has to pick. Otherwise the caller proceeds to candidate
    selection with the returned `preferred_position` and `reason`.
    """
    if force_weakest:
        return (
            weakest_outfield_position(my_squad, biwenger_players),
            _reason_force_weakest(),
            None,
        )
    if force_position is not None:
        return force_position, _reason_force_position(force_position), None

    needs_selector = len(losses) > 1 or (
        len(losses) == 1 and len(losses[0]["alt_positions"]) > 0
    )
    if needs_selector:
        positions = unique_outfield_positions(losses)
        if positions:
            _send(
                _format_selector_text(losses, cash),
                reply_markup=_selector_keyboard(positions),
            )
            return 0, "", {"cash": cash, "losses": losses, "selector": True}
        # Every loss was a goalkeeper: no outfield line to offer.
        _send(_format_goalkeeper_losses_text(losses, cash))
        return 0, "", {"cash": cash, "losses": losses, "goalkeeper_only": True}

    if len(losses) == 1 and losses[0]["position_id"] in OUTFIELD_POSITION_IDS:
        return losses[0]["position_id"], _reason_single_loss(losses[0]), None
    return (
        weakest_outfield_position(my_squad, biwenger_players),
        _reason_no_losses() if not losses else _reason_goalkeeper_loss(losses[0]),
        None,
    )


def execute_clausulazo(player_id: int, owner_user_id: int, amount: int) -> dict:
    """Place the approved clausulazo and notify Telegram with the result.

    `player_id`/`owner_user_id`/`amount` are the values the user saw and
    approved in the preview. We do NOT recompute candidates here; if
    cash dropped between preview and confirm Biwenger rejects and we
    surface the error.
    """
    biwenger = build_biwenger_session()
    try:
        offer = biwenger.place_clausulazo(
            player_id=int(player_id),
            amount=int(amount),
            seller_user_id=int(owner_user_id),
            offers_url=config.OFFERS_URL,
        )
    except Exception as exc:
        logger.warning(
            "Emergency clausulazo failed.",
            extra={"player_id": player_id, "amount": amount, "error": str(exc)},
        )
        _send(f"❌ <b>Clausulazo rechazado</b> — <code>{_escape(str(exc))}</code>")
        raise

    # Resolve the player name for the success message — the callback
    # only carries the id and we want the chat to read "Pagado X € por
    # Iago Aspas" not "por jugador 1523".
    players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    player_name = (players.get(int(player_id)) or {}).get(
        "name"
    ) or f"jugador {player_id}"
    cash_after = int(biwenger.get_account_state().get("cash") or 0)
    _send(_format_executed_text(int(amount), player_name, cash_after))
    return {
        "player_id": int(player_id),
        "amount": int(amount),
        "offer_id": offer.get("id"),
        "status": offer.get("status"),
        "cash_after": cash_after,
    }


def _requirement_for_formation(label: str) -> dict:
    """`{line: needed}` for the formation label the plan was built against —
    reusing the plan's own choice rather than re-running `target_formation`,
    which could pick a different shape now and shuffle which lines count as
    holes."""
    for formation_label, n_def, n_mid, n_fwd in rebuild.FORMATIONS:
        if formation_label == label:
            return {GK: 1, DEF: n_def, MID: n_mid, FWD: n_fwd}
    raise ValueError(f"unknown formation: {label}")


def execute_rebuild(plan_id: str) -> dict:
    """Claim a stored rebuild plan and execute it, one signing at a time,
    reporting each outcome as it happens.

    Claims before spending: `rebuild_store.claim` reads and deletes the
    document in one Firestore transaction, so a duplicate call for the same
    `plan_id` — a crash-triggered retry, a fast double tap on the confirm
    button, or an older plan a newer one has superseded — finds nothing and
    never reaches `place_clausulazo`. This is at-most-once, not resumable:
    a crash partway through the loop below loses whatever signings had not
    yet been attempted, and the owner has to re-run `/emergencia`.

    A plan older than `config.REBUILD_PLAN_TTL_SECONDS` is refused — clause
    values move — but it has already been claimed by this point, so
    refusing it never reopens the double-execution window `claim` closes.

    The squad is re-read fresh before anything is spent. If it can already
    field a legal eleven — another plan, or a manual transfer, beat this
    one to it — nothing is bought. Otherwise each signing's own line is
    checked against the CURRENT deficit for the plan's formation: a hole
    the plan meant to fill but that is not short any more is skipped.

    Re-reads the candidate pool fresh rather than trusting anything else
    from plan time: a target that is gone, no longer affordable, or whose
    clause rose above what the plan approved for it (`clause_at_plan`) is
    replaced by the best-value candidate in the SAME line at or under that
    SAME price — which by construction leaves the approved target eligible
    for its own hole — never a swap paid for out of another hole's money,
    and never a goalkeeper. A hole with nothing left within that price is
    reported unfilled, never retried against the rest of the budget.

    An exception stops the loop rather than continuing: a call that timed
    out may have gone through anyway, and there is no way to tell from here
    — continuing on a squad this code can no longer describe is how a
    purchase that actually succeeded gets attempted a second time. Every
    attempted signing's outcome is sent to Telegram the moment it resolves,
    not batched at the end, so a request that outlives gunicorn's timeout
    does not take every purchase already made down with it; a signing left
    unattempted because the loop already stopped is still in the returned
    list, just not sent on its own — the failure message already said the
    plan stopped.

    Bench signings carry no eleven hole to be checked against `remaining_holes`
    at all — they are bought when the exact player is still there and within
    `clause_at_plan`, or reported unavailable, never swapped for another body.
    Signings are processed eleven-first regardless of storage order, so a
    bench purchase can never spend the reserve an eleven hole still needs.
    """
    doc = rebuild_store.claim(plan_id)
    if doc is None:
        logger.info(
            "Rebuild plan missing or already executed.", extra={"plan_id": plan_id}
        )
        _send(_format_rebuild_missing_text())
        return {"plan_id": plan_id, "status": "not_found"}

    if time.time() - doc["created_at"] > config.REBUILD_PLAN_TTL_SECONDS:
        _send(_format_rebuild_expired_text())
        return {"plan_id": plan_id, "status": "expired"}

    ctx = build_context()
    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_ids = {p.get("id") for p in my_squad if p.get("id") is not None}
    my_rows = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    elig = rebuild.eligibilities(my_rows)

    if composition_ok(elig):
        _send(_format_rebuild_not_needed_text())
        return {"plan_id": plan_id, "status": "not_needed", "signings": []}

    remaining_holes = rebuild.line_deficit(
        elig, _requirement_for_formation(doc["formation"])
    )
    rivals = gather_rivals(ctx.biwenger, ctx.biwenger_players, ctx.jp_index)

    outcomes = []
    bought_rows = []
    stopped = False
    signings = sorted(doc["signings"], key=lambda s: s.get("bench", False))
    for signing in signings:
        is_bench = signing.get("bench", False)

        if stopped:
            outcome = {"line": signing["line"], "status": "not_attempted"}
            outcomes.append(outcome)
            continue

        if not is_bench and remaining_holes.get(signing["line"], 0) <= 0:
            outcome = {"line": signing["line"], "status": "skipped"}
            outcomes.append(outcome)
            _send(_format_rebuild_signing_text(outcome))
            continue

        cash = int(ctx.biwenger.get_account_state().get("cash") or 0)
        pool = filter_affordable(rivals, my_ids, target=cash)

        if is_bench:
            swapped = False
            chosen = next(
                (
                    row
                    for row in pool
                    if row.get("position_id") != GK
                    and int(row["bw_id"]) == int(signing["bw_id"])
                    and row["clause_value"] <= signing["clause_at_plan"]
                ),
                None,
            )
            if chosen is None:
                outcome = {"line": signing["line"], "status": "unavailable"}
                outcomes.append(outcome)
                _send(_format_rebuild_signing_text(outcome))
                continue
        else:
            line_pool = [
                row
                for row in pool
                if row.get("position_id") != GK
                and rebuild._eligible_for(row, signing["line"])
                and row["clause_value"] <= signing["clause_at_plan"]
            ]
            current = next(
                (
                    row
                    for row in line_pool
                    if int(row["bw_id"]) == int(signing["bw_id"])
                ),
                None,
            )
            swapped = current is None
            chosen = current or (
                max(line_pool, key=rebuild.value_of) if line_pool else None
            )
            if chosen is None:
                outcome = {"line": signing["line"], "status": "unfilled"}
                outcomes.append(outcome)
                _send(_format_rebuild_signing_text(outcome))
                continue

        try:
            ctx.biwenger.place_clausulazo(
                player_id=int(chosen["bw_id"]),
                amount=int(chosen["clause_value"]),
                seller_user_id=int(chosen["owner_user_id"]),
                offers_url=config.OFFERS_URL,
            )
        except Exception as exc:
            logger.warning(
                "Rebuild signing failed — outcome unknown, stopping the plan.",
                extra={
                    "plan_id": plan_id,
                    "bw_id": chosen["bw_id"],
                    "error": str(exc),
                },
            )
            outcome = {"line": signing["line"], "status": "unknown", "error": str(exc)}
            outcomes.append(outcome)
            _send(_format_rebuild_signing_text(outcome))
            stopped = True
            continue

        my_ids.add(chosen["bw_id"])
        bought_rows.append(chosen)
        if not is_bench:
            remaining_holes[signing["line"]] = (
                remaining_holes.get(signing["line"], 0) - 1
            )
        outcome = {
            "line": signing["line"],
            "status": "bought",
            "swapped": swapped,
            "bw_id": chosen["bw_id"],
            "name": chosen["name"],
            "amount": chosen["clause_value"],
        }
        outcomes.append(outcome)
        _send(_format_rebuild_signing_text(outcome))

    cash_after = int(ctx.biwenger.get_account_state().get("cash") or 0)
    fields_xi = xi_snapshot(my_rows + bought_rows) is not None
    _send(_format_rebuild_summary_text(outcomes, cash_after, fields_xi))
    return {"plan_id": plan_id, "signings": outcomes, "cash_after": cash_after}


# --- Side-effect helpers -------------------------------------------------


def _escape(text: str) -> str:
    """HTML-escape for Telegram parse_mode=HTML."""
    return html.escape(text, quote=False)


def _send(text: str, reply_markup: Optional[dict] = None) -> None:
    telegram = require_telegram()
    if telegram is None:
        logger.warning("Telegram missing — emergency message dropped.")
        return
    token, chat_id = telegram
    send_telegram_message_or_raise(
        bot_token=token, chat_id=chat_id, text=text, reply_markup=reply_markup
    )


# Re-export the outfield set so callers that need the canonical tuple
# (e.g. the recommendations message) don't have to know which module
# owns it. Keeps the dependency arrow pointing into `clausulazo_detection`.
__all__ = [
    "preview_clausulazo",
    "execute_clausulazo",
    "execute_rebuild",
    "OUTFIELD_POSITION_IDS",
]
