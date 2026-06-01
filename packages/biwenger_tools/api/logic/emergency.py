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
from packages.biwenger_tools.api.logic.orchestration import (
    build_biwenger_session,
    build_context,
    require_telegram,
)
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

    league_users = biwenger.get_league_users(config.LEAGUE_DATA_URL)
    my_manager_name = league_users.get(int(biwenger.user_id), "")

    losses = recent_lost_players(
        biwenger, ctx.biwenger_players, my_manager_name, now_epoch=time.time()
    )

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

    if len(losses) == 1:
        return losses[0]["position_id"], _reason_single_loss(losses[0]), None
    return (
        weakest_outfield_position(my_squad, biwenger_players),
        _reason_no_losses(),
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
    "OUTFIELD_POSITION_IDS",
]
