"""Emergency clausulazo — `POST /emergency/clausulazo/{preview,execute}`.

Manual, on-demand operation triggered from the Telegram bot via
`/emergencia`. Two phases:

1. **Preview** — read my cash, decide which position needs reinforcing
   (the line I just lost to a recent clausulazo, or the weakest outfield
   line if none), pick the best affordable rival in that position, and
   post a confirmation message with inline-keyboard buttons.
2. **Execute** — fired by the bot when the user taps "Sí" on the inline
   keyboard. Calls `place_clausulazo` against the exact `player_id` /
   `owner_user_id` / `amount` the user approved, and notifies the
   result.

Hard rules:

- Cash is **justo** — `target = cash` (no dynamic margin, unlike
  `/recomendar`). The op must never push me into the red.
- `amount = clause_value` exactly — minimum valid clausulazo, no inflation.
- Multi-position players lost are NOT used to pick a target position
  (their loss is ambiguous → fall back to the weakest-line rule).
- Never clause a rival's only GK (shared `filter_affordable` house rule).
"""

import time
from typing import Optional

from core.sdk.biwenger import BiwengerClient
from core.sdk.telegram import send_telegram_message_or_raise
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.clausulazo_candidates import (
    filter_affordable,
    gather_rivals,
    sf_of,
)
from packages.biwenger_tools.api.logic.orchestration import (
    build_biwenger_session,
    build_context,
    require_telegram,
)
from packages.biwenger_tools.api.player_formatting import POSITION_SHORT

logger = get_logger(__name__)

RECENT_CLAUSULAZO_WINDOW_SECONDS = 24 * 60 * 60

# Position-pick order when reinforcing the weakest line. GK is out of
# scope (we don't clausulazo a GK on emergency). DEF goes first on
# ties, then MID, then FWD — the lower-cost positions cover faster.
_OUTFIELD_POSITION_IDS = (2, 3, 4)
_POSITION_LABELS_ES = {1: "Portero", 2: "Defensa", 3: "Centrocampista", 4: "Delantero"}


def _euros(n: int | None) -> str:
    if n is None:
        return "—"
    s = f"{int(n):,}".replace(",", ".")
    return f"{s} €"


def _is_multi_position(bw_player: dict) -> bool:
    """A multi-position player has at least one `altPositions` entry."""
    return bool(bw_player.get("altPositions") or [])


def _recent_lost_players(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    my_manager_name: str,
    now_epoch: float,
) -> list[dict]:
    """Every clausulazo against me in the last 24h, resolved against the
    cf-base players map.

    Returns a list of `{player_id, name, position_id, alt_positions, date}`
    in board order (which Biwenger does NOT guarantee to be chronological:
    multiple clausulazos that arrive in the same batch share the entry's
    `date`, so we can't order them reliably by that field — the caller
    is the one that decides what to do when there's more than one).

    Detection compares `from.id == biwenger.user_id` first; some board
    payload variants only expose `from.name`, so we fall back to a name
    match. Either is sufficient — we own both sides of the lookup.
    """
    raw = biwenger.get_all_clausulazos(config.CLAUSULAZOS_URL)
    entries = raw.get("data", []) or []
    if isinstance(entries, dict):
        entries = list(entries.values())

    cutoff = now_epoch - RECENT_CLAUSULAZO_WINDOW_SECONDS
    losses: list[dict] = []
    for entry in entries:
        entry_date = entry.get("date", 0) or 0
        if entry_date < cutoff:
            continue
        for item in entry.get("content") or []:
            if item.get("type") != "clause":
                continue
            from_obj = item.get("from") or {}
            from_id = from_obj.get("id")
            from_name = from_obj.get("name")
            is_me = (from_id is not None and int(from_id) == int(biwenger.user_id)) or (
                from_name and my_manager_name and from_name == my_manager_name
            )
            if not is_me:
                continue
            player_ref = item.get("player")
            player_id = (
                player_ref.get("id") if isinstance(player_ref, dict) else player_ref
            )
            bw_player = biwenger_players.get(player_id)
            if not bw_player:
                continue
            losses.append(
                {
                    "player_id": player_id,
                    "name": bw_player.get("name"),
                    "position_id": bw_player.get("position"),
                    "alt_positions": bw_player.get("altPositions") or [],
                    "date": entry_date,
                }
            )
    return losses


def _unique_positions(losses: list[dict]) -> list[int]:
    """Outfield positions a loss touches (primary + alts), DEF/MID/FWD order.

    Used to build the selector buttons: one per distinct outfield
    position the recent losses imply. GK is excluded — we never
    clausulazo a GK on emergency.
    """
    found: set[int] = set()
    for loss in losses:
        for pos in (loss["position_id"], *loss["alt_positions"]):
            if pos in _OUTFIELD_POSITION_IDS:
                found.add(pos)
    return [p for p in _OUTFIELD_POSITION_IDS if p in found]


def _weakest_outfield_position(my_squad: list, biwenger_players: dict) -> int:
    """Position id with the fewest players among DEF/MID/FWD.

    Ties break in DEF > MID > FWD order — lower-tier positions get
    filled first because affordable replacements are easier to find.
    """
    counts = {pos: 0 for pos in _OUTFIELD_POSITION_IDS}
    for entry in my_squad:
        bw_player = biwenger_players.get(entry.get("id"))
        if not bw_player:
            continue
        pos = bw_player.get("position")
        if pos in counts:
            counts[pos] += 1
    # Tie-break order: iterate _OUTFIELD_POSITION_IDS so DEF (2) wins
    # over MID (3) over FWD (4) when counts are equal.
    return min(_OUTFIELD_POSITION_IDS, key=lambda pos: (counts[pos], pos))


def _pick_target(
    candidates: list[dict], preferred_position: int
) -> tuple[Optional[dict], str]:
    """Top SF in `preferred_position`; fall back to top SF overall.

    Returns `(candidate, fallback_note)`. `fallback_note` is empty if a
    candidate in the preferred position was found, non-empty otherwise
    so the message can say "no DEF afford(able), going for the best
    SF instead".
    """
    in_position = [c for c in candidates if c.get("position_id") == preferred_position]
    if in_position:
        in_position.sort(key=sf_of, reverse=True)
        return in_position[0], ""
    if not candidates:
        return None, ""
    candidates_sorted = sorted(candidates, key=sf_of, reverse=True)
    return candidates_sorted[0], (
        f"sin candidatos en {_POSITION_LABELS_ES[preferred_position]}, "
        "voy al mejor SF disponible"
    )


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
    `e:m` triggers the weakest-line fallback (lets the user override the
    auto-detected positions when they prefer to plug a different gap).
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


def _format_selector_text(losses: list[dict], cash: int) -> str:
    """Render the multi-loss selector message.

    Lists every recent loss with its position(s) so the user can see
    what happened, then asks which line to reinforce. Multi-position
    players show both positions (e.g. `DEF/MED`).
    """
    lines = [
        "🚨 <b>Emergencia — varias pérdidas recientes</b>",
        "",
        "Tu cash: <b>" + _euros(cash) + "</b>",
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
        f"Cláusula: <b>{_euros(target['clause_value'])}</b> · "
        f"SF {sf_of(target)}\n"
        f"Tu cash: <b>{_euros(cash)}</b>\n"
        f"\n"
        f"<i>Esta operación es irreversible.</i>"
    )


def preview_clausulazo(
    force_position: Optional[int] = None, force_weakest: bool = False
) -> dict:
    """Compute the target + reason and post the confirmation message.

    Behaviour depends on the recent clausulazos against me:
    - 0 losses → reinforce weakest outfield line.
    - 1 single-position loss → target that position directly.
    - Otherwise (>1 loss, or 1 multi-position loss) → post a selector
      message with one button per outfield position involved + a
      "weakest line" fallback. The user's tap re-enters this function
      with `force_position` or `force_weakest`, which short-circuits
      the detection and goes straight to the Sí/No preview.

    Side effect: one Telegram message (selector OR confirmation). The
    returned dict is for diagnostics only — the user-visible artefact
    is the Telegram message.
    """
    ctx = build_context()
    biwenger = ctx.biwenger

    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_ids = {p.get("id") for p in my_squad if p.get("id") is not None}
    cash = int(biwenger.get_account_state(my_squad, ctx.biwenger_players)["cash"])

    league_users = biwenger.get_league_users(config.LEAGUE_DATA_URL)
    my_manager_name = league_users.get(int(biwenger.user_id), "")

    losses = _recent_lost_players(
        biwenger, ctx.biwenger_players, my_manager_name, now_epoch=time.time()
    )

    # --- Decide preferred_position + reason --------------------------------
    if force_weakest:
        preferred_position = _weakest_outfield_position(my_squad, ctx.biwenger_players)
        reason = "refuerza la línea más mermada (elegido)"
    elif force_position is not None:
        preferred_position = force_position
        reason = (
            f"refuerza la línea de "
            f"{_POSITION_LABELS_ES[force_position].lower()}s (elegido)"
        )
    else:
        # Auto-detect from recent losses. Two ambiguous cases trigger the
        # selector: more than one loss, or a single loss that's
        # multi-position. The selector lets the user disambiguate
        # because the board batches transfers under a shared date and
        # we can't reliably tell which is the most recent within the batch.
        unique_positions = _unique_positions(losses)
        needs_selector = len(losses) > 1 or (
            len(losses) == 1 and len(losses[0]["alt_positions"]) > 0
        )
        if needs_selector and unique_positions:
            text = _format_selector_text(losses, cash)
            _send(text, reply_markup=_selector_keyboard(unique_positions))
            return {
                "cash": cash,
                "losses": losses,
                "selector": True,
            }

        if len(losses) == 1:
            loss = losses[0]
            preferred_position = loss["position_id"]
            reason = (
                f"acaban de clausularte un "
                f"{_POSITION_LABELS_ES[preferred_position].lower()} "
                f"({loss['name']}) en las últimas 24h — refuerza esa línea"
            )
        else:
            preferred_position = _weakest_outfield_position(
                my_squad, ctx.biwenger_players
            )
            reason = (
                "sin clausulazos recientes contra ti — " "refuerza la línea más mermada"
            )

    # --- Pick target + send confirmation ----------------------------------
    rivals = gather_rivals(biwenger, ctx.biwenger_players, ctx.jp_index)
    affordable = filter_affordable(rivals, my_ids, target=cash)
    target, fallback_note = _pick_target(affordable, preferred_position)

    payload = {
        "cash": cash,
        "preferred_position": preferred_position,
        "losses": losses,
    }

    if target is None:
        text = (
            f"🚨 <b>Emergencia</b>\n"
            f"\n"
            f"Sin candidatos asequibles. Tu cash: <b>{_euros(cash)}</b>. "
            f"Motivo: <i>{reason}</i>."
        )
        _send(text)
        return {**payload, "target": None, "reason": reason}

    text = _format_preview_text(target, reason, fallback_note, cash)
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


def execute_clausulazo(player_id: int, owner_user_id: int, amount: int) -> dict:
    """Place the approved clausulazo and notify Telegram with the result.

    `player_id`, `owner_user_id` and `amount` come from the inline
    keyboard payload the bot forwards — i.e. the exact values the user
    saw and approved in the preview. We do NOT recompute candidates
    here; if cash dropped between preview and confirm Biwenger will
    reject and we surface the error.
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

    # Resolve the player name for the success message. The execute
    # endpoint only receives ids (callback_data is capped at 64 bytes),
    # so the preview's player name doesn't survive the round-trip; we
    # look it up against the cf-base players map.
    players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    player_name = (players.get(int(player_id)) or {}).get(
        "name"
    ) or f"jugador {player_id}"
    cash_after = int(biwenger.get_account_state().get("cash") or 0)
    _send(
        f"🚨 <b>Clausulazo ejecutado</b>\n"
        f"\n"
        f"Pagado <b>{_euros(amount)}</b> por <b>{_escape(player_name)}</b>.\n"
        f"Cash restante: <b>{_euros(cash_after)}</b>"
    )
    return {
        "player_id": int(player_id),
        "amount": int(amount),
        "offer_id": offer.get("id"),
        "status": offer.get("status"),
        "cash_after": cash_after,
    }


def _escape(text: str) -> str:
    """HTML-escape for Telegram parse_mode=HTML."""
    import html

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
