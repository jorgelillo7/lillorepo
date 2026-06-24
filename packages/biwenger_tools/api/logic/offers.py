"""Inbox de ofertas — listing, scoring + accept/reject.

Powers `/ofertas` (bot on-demand) and the offers step chained at the end of
`/digests/daily`. Per-offer flow:

1. Fetch pending offers via `BiwengerClient.get_received_offers()`.
2. Score each one — tier from `auto_bid`, ROI vs `owner.price` (lo que
   pagaste), delta vs cf-base, is-in-current-11.
3. Post one Telegram message per offer with [✅] [❌] [⏰] inline buttons.

Decisions taken with `decide_offer(offer_id, "accepted"|"rejected")`
(SDK → `PUT /api/v2/offers/{id}`). Ignore is bot-side only (edits the
message, never hits Biwenger).
"""

from datetime import datetime
from html import escape
from typing import Optional

from core.constants import MADRID_TZ
from core.sdk.jp import get_predict_rate
from core.sdk.telegram import send_telegram_message
from core.utils import format_euros, get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import auto_bid as ab
from packages.biwenger_tools.api.logic.lineup import pick_lineup
from packages.biwenger_tools.api.logic.orchestration import (
    OrchestratorContext,
    build_biwenger_session,
    build_context,
    require_telegram,
)
from packages.biwenger_tools.api.logic.rows import build_squad_rows

logger = get_logger(__name__)


POSITION_NAMES = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}

# Decision verbs. Match the Biwenger PUT body literally.
DECISION_ACCEPT = "accepted"
DECISION_REJECT = "rejected"
VALID_DECISIONS = (DECISION_ACCEPT, DECISION_REJECT)

# Recommendation tags surfaced to the user.
REC_ACCEPT = "ACEPTAR"
REC_REJECT = "RECHAZAR"
REC_DOUBTFUL = "DUDOSO"

# Thresholds for the recommendation algorithm. Tier mapping reuses
# `auto_bid` directly — same source of truth across the project.
# Why these specific cutoffs (vs cf-base):
#  - +15% over market = clearly above fair value, take the money.
#  - -10% under market = clearly underpriced, hold or list publicly.
#  - +25% over market on a star player = override the "never sell" rule
#    because the offer is too good to refuse even for a fijo.
ACCEPT_OVER_MARKET_PCT = 15.0
REJECT_UNDER_MARKET_PCT = -10.0
STAR_OVERRIDE_OVER_MARKET_PCT = 25.0


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_offers_inbox(ctx: Optional[OrchestratorContext] = None) -> dict:
    """Fetch + score the inbox, post one Telegram message per offer.

    `ctx` is optional so the digest can pass the already-built context
    instead of paying a second JP+Biwenger round-trip. When None we build
    one ourselves (manual `/ofertas` from the bot).

    Silent when the inbox is empty — no spam in the daily digest if the
    user has no pending offers.
    """
    ctx = ctx or build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    inbox = ctx.biwenger.get_received_offers()
    if not inbox:
        logger.info("Offers inbox empty — skipping send.")
        return {"sent": 0, "offers": 0}

    # One squad fetch + lineup pick to drive the is-in-current-11 signal.
    # If pick_lineup blows up we fall back to "unknown" gracefully — the
    # recommendation still works, just loses one bit of information.
    starter_ids = _starter_ids(ctx)

    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_team = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    acq_by_id = {row["bw_id"]: row for row in my_team}

    sent = 0
    for offer in inbox:
        scored = _score_offer(offer, ctx, acq_by_id, starter_ids)
        if scored is None:
            logger.warning(
                "Skipping malformed offer.", extra={"offer_id": offer.get("id")}
            )
            continue
        text = _format_offer_message(scored)
        keyboard = _decision_keyboard(scored["offer_id"])
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
        )
        sent += 1

    logger.info("Offers inbox sent.", extra={"offers": len(inbox), "sent": sent})
    return {"sent": sent, "offers": len(inbox)}


def run_offer_decision(offer_id: int, decision: str) -> dict:
    """Forward an accept/reject decision to Biwenger + confirm to Telegram.

    `decision` must be one of `VALID_DECISIONS`. Returns the SDK's response
    dict for diagnostics. Caller (the route handler) translates failures
    into 5xx so the bot can post a fallback error.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {VALID_DECISIONS}, got {decision!r}")
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    # The PUT only needs an authenticated Biwenger session, not JP or
    # players — skip the full context for speed.
    biwenger = build_biwenger_session()
    result = biwenger.decide_offer(int(offer_id), decision)

    final_status = result.get("status")
    if decision == DECISION_ACCEPT:
        icon, verb = "✅", "Aceptada"
    else:
        icon, verb = "❌", "Rechazada"
    send_telegram_message(
        bot_token=token,
        chat_id=chat_id,
        text=(
            f"{icon} <b>Oferta {verb}</b> · id <code>{offer_id}</code> · "
            f"estado final: <code>{escape(str(final_status))}</code>"
        ),
    )
    return {
        "sent": 1,
        "offer_id": offer_id,
        "decision": decision,
        "final_status": final_status,
    }


# ---------------------------------------------------------------------------
# Scoring + recommendation algorithm
# ---------------------------------------------------------------------------


def _starter_ids(ctx: OrchestratorContext) -> set:
    """Resolve the bw_ids that pick_lineup would put in the starting 11.

    Best-effort: any failure returns an empty set (the recommendation
    then treats every offer as non-starter, which is the conservative
    default — losing the "they are a starter, don't sell" guard).
    """
    try:
        my_squad = ctx.biwenger.get_manager_squad(
            config.USER_SQUAD_URL, ctx.biwenger.user_id
        )
        rows = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
        result = pick_lineup(rows)
        if not result:
            return set()
        return {row["bw_id"] for row, _ in result["starters"]}
    except Exception:
        logger.exception("Failed to compute starter set — treating as unknown.")
        return set()


def _tier_label(sf: int) -> str:
    if sf >= ab.TIER_ALL_IN_MIN:
        return f"⭐⭐⭐ Estrella (T1, SF {sf})"
    if sf >= ab.TIER_T2_MIN:
        return f"⭐⭐ Titular fijo (T2, SF {sf})"
    if sf >= ab.TIER_T3_MIN:
        return f"⭐ Rotación (T3, SF {sf})"
    if sf >= ab.TIER_T4_MIN:
        return f"⬇️ Fondo de armario (T4, SF {sf})"
    return f"❌ Descarte (SF {sf})"


def _score_offer(
    offer: dict, ctx: OrchestratorContext, acq_by_id: dict, starter_ids: set
) -> Optional[dict]:
    """Enrich one offer with all the signals + a recommendation."""
    rp = offer.get("requestedPlayers") or []
    if not rp:
        return None
    raw = rp[0]
    player_id = raw["id"] if isinstance(raw, dict) else int(raw)
    bw = ctx.biwenger_players.get(player_id) or {}
    name = bw.get("name") or f"id={player_id}"
    cf_price = int(bw.get("price") or 0)
    position = POSITION_NAMES.get(bw.get("position"), "?")

    jp_player = (acq_by_id.get(player_id) or {}).get("jp_player")
    sf = get_predict_rate(jp_player or {}, 2) or 0

    acq_row = acq_by_id.get(player_id) or {}
    acq_price = acq_row.get("acq_price") or 0
    acq_date = acq_row.get("acq_date")
    acq_from = acq_row.get("acq_from")

    offer_amount = int(offer.get("amount") or 0)
    roi = (offer_amount - acq_price) if acq_price else None
    roi_pct = (roi / acq_price * 100) if (acq_price and roi is not None) else None
    vs_market = (offer_amount - cf_price) if cf_price else None
    vs_market_pct = (
        (vs_market / cf_price * 100) if (cf_price and vs_market is not None) else None
    )
    is_starter = player_id in starter_ids

    frm = offer.get("from")
    if frm and frm.get("id"):
        offerer = f"👤 {frm.get('name') or 'rival'}"
    else:
        offerer = "🤖 Mercado público"

    recommendation, reasons = _recommend(
        sf=sf,
        roi_pct=roi_pct,
        vs_market_pct=vs_market_pct,
        is_starter=is_starter,
    )

    return {
        "offer_id": offer["id"],
        "player_id": player_id,
        "name": name,
        "position": position,
        "offer_amount": offer_amount,
        "acq_price": acq_price,
        "acq_date": acq_date,
        "acq_from": acq_from,
        "roi": roi,
        "roi_pct": roi_pct,
        "cf_price": cf_price,
        "vs_market": vs_market,
        "vs_market_pct": vs_market_pct,
        "sf": sf,
        "tier_label": _tier_label(sf),
        "is_starter": is_starter,
        "offerer": offerer,
        "until": offer.get("until"),
        "recommendation": recommendation,
        "reasons": reasons,
    }


def _recommend(
    *,
    sf: int,
    roi_pct: Optional[float],
    vs_market_pct: Optional[float],
    is_starter: bool,
) -> tuple[str, list[str]]:
    """Apply the decision rules in cascade order. First match wins.

    Returns ``(recommendation, reasons)`` where ``recommendation`` is
    one of ``REC_ACCEPT``, ``REC_REJECT``, ``REC_DOUBTFUL``.
    """
    reasons: list[str] = []

    # 1. Estrella o titular fijo en el 11 → RECHAZAR salvo oferta indecente.
    if sf >= ab.TIER_ALL_IN_MIN or (sf >= ab.TIER_T2_MIN and is_starter):
        if vs_market_pct is not None and vs_market_pct >= STAR_OVERRIDE_OVER_MARKET_PCT:
            reasons.append(
                f"Titular fuerte (SF {sf}) pero oferta "
                f"{vs_market_pct:+.0f}% sobre cf-base"
            )
            return REC_DOUBTFUL, reasons
        reasons.append(
            f"Titular fijo / estrella (SF {sf}); no se vende salvo oferta indecente"
        )
        return REC_REJECT, reasons

    # 2. Descarte o fondo de armario con plusvalía → ACEPTAR.
    if sf < ab.TIER_T3_MIN and roi_pct is not None and roi_pct > 0:
        reasons.append(
            f"Fondo de armario (SF {sf}) y plusvalía {roi_pct:+.0f}% vs compra"
        )
        return REC_ACCEPT, reasons

    # 3. Oferta claramente por encima del valor cf-base → ACEPTAR.
    if vs_market_pct is not None and vs_market_pct >= ACCEPT_OVER_MARKET_PCT:
        reasons.append(f"Oferta {vs_market_pct:+.0f}% sobre cf-base — buen momento")
        return REC_ACCEPT, reasons

    # 4. Oferta claramente baja → RECHAZAR.
    if vs_market_pct is not None and vs_market_pct <= REJECT_UNDER_MARKET_PCT:
        reasons.append(
            f"Oferta {vs_market_pct:+.0f}% bajo cf-base; aguanta o lánzalo al mercado"
        )
        return REC_REJECT, reasons

    # 5. Rotación con oferta razonable → DUDOSO.
    if ab.TIER_T3_MIN <= sf < ab.TIER_T2_MIN:
        reasons.append(f"Rotación (SF {sf}); decide según tu necesidad de cash")
        return REC_DOUBTFUL, reasons

    # 6. Catch-all.
    reasons.append("Caso límite — decide tú")
    return REC_DOUBTFUL, reasons


# ---------------------------------------------------------------------------
# Telegram rendering
# ---------------------------------------------------------------------------


def _decision_keyboard(offer_id: int) -> dict:
    """Inline keyboard with accept / reject / ignore for a single offer."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Aceptar", "callback_data": f"o:a:{offer_id}"},
                {"text": "❌ Rechazar", "callback_data": f"o:r:{offer_id}"},
                {"text": "⏰ Ignorar", "callback_data": f"o:i:{offer_id}"},
            ]
        ]
    }


def _format_offer_message(s: dict) -> str:
    """One Telegram message per offer — everything the user needs to decide.

    Every dynamic value gets HTML-escaped because Telegram's HTML parser
    is strict: a stray `<`/`>`/`&` in a name or status drops the whole
    message with a 400.
    """
    esc = lambda x: escape(str(x), quote=False)  # noqa: E731

    rec = s["recommendation"]
    if rec == REC_ACCEPT:
        rec_icon = "✅"
    elif rec == REC_REJECT:
        rec_icon = "❌"
    else:
        rec_icon = "🤔"

    lines = [
        "📥 <b>Oferta entrante</b>",
        "",
        f"Jugador: <b>{esc(s['name'])}</b> ({esc(s['position'])})",
        f"Ofertante: {esc(s['offerer'])}",
        f"Cantidad: <b>{esc(format_euros(s['offer_amount']))}</b>",
        "",
    ]

    if s["acq_price"]:
        roi_str = ""
        if s["roi"] is not None and s["roi_pct"] is not None:
            sign = "+" if s["roi"] >= 0 else ""
            roi_str = (
                f"  ·  Diff: <b>{sign}{esc(format_euros(s['roi']))} "
                f"({s['roi_pct']:+.0f}%)</b>"
            )
        lines.append(f"Pagaste: {esc(format_euros(s['acq_price']))}{roi_str}")
        if s["acq_from"]:
            lines.append(f"  · Clausulado a: {esc(s['acq_from'])}")
    else:
        lines.append("Pagaste: —  (sin rastro de compra)")

    if s["cf_price"]:
        vm_str = ""
        if s["vs_market_pct"] is not None:
            vm_str = f"  ·  Oferta vs mercado: <b>{s['vs_market_pct']:+.0f}%</b>"
        lines.append(f"Valor cf-base: {esc(format_euros(s['cf_price']))}{vm_str}")

    lines.append(f"Tier: {esc(s['tier_label'])}")
    lines.append(f"En tu 11 actual: <b>{'SÍ' if s['is_starter'] else 'NO'}</b>")

    if s["until"]:
        until_dt = datetime.fromtimestamp(s["until"], MADRID_TZ)
        lines.append(f"Expira: {until_dt.strftime('%d/%m %H:%M')}")

    lines.append("")
    lines.append(f"<b>Recomendación: {rec_icon} {esc(rec)}</b>")
    for reason in s["reasons"]:
        lines.append(f"  · {esc(reason)}")

    return "\n".join(lines)
