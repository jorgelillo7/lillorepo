"""Inbox de ofertas — listing, scoring + accept/reject.

Powers `/ofertas` (bot on-demand) and the offers step chained at the end of
`/digests/daily`. Per-offer flow:

1. Fetch pending offers via `BiwengerClient.get_received_offers()`.
2. Score each one on two independent axes. **Money**: ROI vs `owner.price`
   (lo que pagaste) and delta vs cf-base. **Squad**: is he in the current
   eleven, and what does the eleven lose without him (`XI_LOSS_REJECT`).
   JP's projection band is reported but never stands in for squad role —
   conflating the two is what recommended selling a first-choice keeper.
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
from packages.biwenger_tools.api.logic import lineup
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

# Loss-aversion threshold. A T3+ player with this much paper loss is a
# clear REJECT (you paid X, they offer < X * (1 - LOSS_THRESHOLD)). User
# feedback 25/06: T2 titular paid 14M, offered 7M (-50% ROI) was scored
# DUDOSO. Algorithm previously needed is_starter=True for T2 to reject,
# and is_starter is flaky because pick_lineup excludes players JP has no
# SF for. This rule kicks in regardless of the starter signal.
REJECT_LOSS_PCT = -25.0

# What selling a player costs the starting eleven, in projected SF: the best
# XI with him minus the best XI without him. Computed by re-running the
# `/alinear` optimizer over the squad minus that player, so it prices what a
# hand-rolled "compare him to the next man up" cannot:
#
#  - **Position scarcity.** Sell the only goalkeeper who plays and the slot
#    falls to a substitute keeper projecting 12, not to your best outfielder.
#  - **Formation slack.** Sell the fifth defender when the optimizer fields
#    three and the XI does not change at all — the loss is zero.
#  - **Multi-position cover.** A DEF/MED who was covering midfield is only as
#    expensive as the reshuffle he forces.
#
# The bands. A player's projection tops out around 700, so:
#  - ≥ 150 lost is a hole the squad cannot cover — refuse.
#  - 50–150 is a real but survivable dent — the user decides.
#  - < 150 leaves the money rules in charge, which is the right outcome for
#    depth nobody fields.
XI_LOSS_REJECT = 150
XI_LOSS_DOUBTFUL = 50


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_offers_inbox(
    ctx: Optional[OrchestratorContext] = None,
    *,
    notify_empty: bool = False,
) -> dict:
    """Fetch + score the inbox, post one Telegram message per offer.

    `ctx` is optional so the digest can pass the already-built context
    instead of paying a second JP+Biwenger round-trip. When None we build
    one ourselves (manual `/ofertas` from the bot).

    `notify_empty` controls the empty-inbox UX:
      - `False` (default) — digest mode: stay silent so a morning with no
        pending offers doesn't add noise to the briefing.
      - `True` — on-demand `/ofertas` from the bot: send a "📭 Sin ofertas
        pendientes" message so the user gets a clear answer instead of
        staring at the "procesando…" line forever.
    """
    ctx = ctx or build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    inbox = ctx.biwenger.get_received_offers()
    if not inbox:
        logger.info("Offers inbox empty — skipping send.")
        if notify_empty:
            send_telegram_message(
                bot_token=token,
                chat_id=chat_id,
                text="📭 <b>Sin ofertas pendientes.</b>",
            )
            return {"sent": 1, "offers": 0}
        return {"sent": 0, "offers": 0}

    # The is-in-current-11 signal. Best-effort: a failure leaves the
    # recommendation one input short rather than dropping the inbox.
    starter_ids = _starter_ids(ctx)

    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_team = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    acq_by_id = {row["bw_id"]: row for row in my_team}

    sent = 0
    for offer in inbox:
        scored = _score_offer(offer, ctx, acq_by_id, starter_ids, my_team)
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
    """Resolve the bw_ids currently in the user's Biwenger starting 11.

    Reads the actual lineup Biwenger has stored (whatever the user set
    last) — NOT what `pick_lineup` thinks is optimal. Two reasons:

    1. The user's perception of "está en mi 11" is "está alineado en
       Biwenger ahora mismo", not "el algoritmo lo metería".
    2. `pick_lineup` returns None when a valid 11 can't be formed (a
       squad with 1 player + 10 empty slots, for example), and that
       silently flips every player's is_starter to False — a real-world
       case reported 25/06 where a fixed starter showed as "En tu 11: NO".

    Best-effort: any failure returns an empty set so the recommendation
    still works without this signal.
    """
    try:
        return ctx.biwenger.get_current_lineup_player_ids()
    except Exception:
        logger.exception("Failed to fetch current lineup — treating as unknown.")
        return set()


def _tier_label(sf: int) -> str:
    """The JP projection band, in the vocabulary of a *projection*.

    These used to read "Titular fijo" / "Rotación" / "Fondo de armario" —
    `auto_bid`'s tiers, which answer "what should I pay for a stranger on the
    open market". Printed against a player already in the squad they answer a
    different question than the one they appear to, and got it wrong: the
    user's first-choice goalkeeper came back labelled "⭐ Rotación" purely
    because JP projected him 404 that week. Squad role is now its own line,
    computed from the squad — see `_role_line`.
    """
    if sf >= ab.TIER_ALL_IN_MIN:
        return f"⭐⭐⭐ Proyección top (SF {sf})"
    if sf >= ab.TIER_T2_MIN:
        return f"⭐⭐ Proyección alta (SF {sf})"
    if sf >= ab.TIER_T3_MIN:
        return f"⭐ Proyección media (SF {sf})"
    if sf >= ab.TIER_T4_MIN:
        return f"⬇️ Proyección baja (SF {sf})"
    return f"❌ Sin proyección (SF {sf})"


def _xi_impact(my_team: list, player_id: int) -> dict:
    """What losing this player would do to the best eleven.

    Returns `{"xi_loss": int | None, "breaks_xi": bool}`:

      - `breaks_xi` — the squad cannot field a legal eleven without him at
        all (he is the last player who can cover a slot). The strongest
        "do not sell" signal there is, and the reason it is separate from a
        number: there is no SF total to subtract from.
      - `xi_loss` — projected SF the eleven gives up, `None` when the signal
        is unavailable (no baseline eleven, or the optimizer raised).

    Best-effort throughout: a failure here costs the recommendation one
    input, and is never worth dropping the offer message over.
    """
    try:
        base = lineup.xi_total_sf(my_team)
        if base is None:
            return {"xi_loss": None, "breaks_xi": False}
        without = lineup.xi_total_sf(
            [row for row in my_team if row.get("bw_id") != player_id]
        )
        if without is None:
            return {"xi_loss": None, "breaks_xi": True}
        return {"xi_loss": max(0, base - without), "breaks_xi": False}
    except Exception:
        logger.exception("XI impact failed — scoring without the depth signal.")
        return {"xi_loss": None, "breaks_xi": False}


def _replacement(my_team: list, player_id: int, position_id) -> Optional[dict]:
    """The squad's next man up at that position — who actually covers the hole.

    Names the player the XI-loss number is about, because "pierdes 390 SF" is
    an abstraction and "tu recambio es Fortuño (SF 12)" is the answer to the
    question the user asked out loud.
    """
    if position_id is None:
        return None
    pool = [
        row
        for row in my_team
        if row.get("bw_id") != player_id
        and position_id
        in ({row.get("position_id")} | set(row.get("alt_positions") or []))
    ]
    if not pool:
        return None
    return max(
        pool, key=lambda row: get_predict_rate(row.get("jp_player") or {}, 2) or 0
    )


def _score_offer(
    offer: dict,
    ctx: OrchestratorContext,
    acq_by_id: dict,
    starter_ids: set,
    my_team: Optional[list] = None,
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

    my_team = my_team or []
    impact = _xi_impact(my_team, player_id)
    replacement = _replacement(my_team, player_id, bw.get("position"))
    replacement_sf = (
        get_predict_rate(replacement.get("jp_player") or {}, 2) or 0
        if replacement
        else None
    )

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
        xi_loss=impact["xi_loss"],
        breaks_xi=impact["breaks_xi"],
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
        "xi_loss": impact["xi_loss"],
        "breaks_xi": impact["breaks_xi"],
        "replacement_name": replacement.get("name") if replacement else None,
        "replacement_sf": replacement_sf,
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
    xi_loss: Optional[int] = None,
    breaks_xi: bool = False,
) -> tuple[str, list[str]]:
    """Apply the decision rules in cascade order. First match wins.

    Returns ``(recommendation, reasons)`` where ``recommendation`` is
    one of ``REC_ACCEPT``, ``REC_REJECT``, ``REC_DOUBTFUL``.

    Two questions, deliberately kept apart. `sf` is how well the provider
    expects the player to *score*; `xi_loss` / `breaks_xi` are what the squad
    loses if he *leaves*. They come apart exactly where this used to fail: a
    goalkeeper projecting 404 is mid-table by SF and irreplaceable by depth,
    because the only other keeper on the books projects 12.

    `is_starter` reads the lineup Biwenger has stored right now (see
    `_starter_ids`) — it is a fact about the squad, not an optimizer guess,
    and it gates the depth rules below. It went unused entirely for a while:
    the parameter was passed in and no branch read it, so "En tu 11 actual:
    SÍ" was printed and then ignored.
    """
    reasons: list[str] = []

    # 0. Sin recambio posible → RECHAZAR. No offer is worth an eleven you
    # cannot field: every empty slot is a flat -4 on the round.
    if breaks_xi:
        reasons.append("Sin él no puedes formar un 11 legal — no hay recambio")
        return REC_REJECT, reasons

    # 1. Estrella o titular fijo (T2+) → RECHAZAR salvo oferta indecente.
    if sf >= ab.TIER_T2_MIN:
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

    # 2. Titular cuyo recambio no cubre el hueco → RECHAZAR.
    # Placed above the money rules on purpose: this is the case where the
    # offer looks fine on every financial axis and selling is still wrong.
    if is_starter and xi_loss is not None and xi_loss >= XI_LOSS_REJECT:
        if vs_market_pct is not None and vs_market_pct >= STAR_OVERRIDE_OVER_MARKET_PCT:
            reasons.append(
                f"Titular sin recambio (tu 11 pierde {xi_loss} SF) pero la oferta "
                f"está {vs_market_pct:+.0f}% sobre cf-base"
            )
            return REC_DOUBTFUL, reasons
        reasons.append(
            f"Es titular y tu 11 pierde {xi_loss} SF sin él — el recambio no cubre"
        )
        return REC_REJECT, reasons

    # 3. Útil (T3+) con pérdida fuerte → RECHAZAR (loss aversion).
    # Excepción: si el mercado paga claramente sobre cf-base, compensa.
    if sf >= ab.TIER_T3_MIN and roi_pct is not None and roi_pct <= REJECT_LOSS_PCT:
        if vs_market_pct is not None and vs_market_pct >= ACCEPT_OVER_MARKET_PCT:
            reasons.append(
                f"Pierdes {roi_pct:+.0f}% sobre compra, pero oferta "
                f"{vs_market_pct:+.0f}% sobre cf-base — compensa"
            )
            return REC_ACCEPT, reasons
        reasons.append(
            f"Jugador útil (SF {sf}); pérdida {roi_pct:+.0f}% sobre compra es excesiva"
        )
        return REC_REJECT, reasons

    # 4. Descarte o fondo de armario con plusvalía → ACEPTAR.
    if sf < ab.TIER_T3_MIN and roi_pct is not None and roi_pct > 0:
        reasons.append(
            f"Fondo de armario (SF {sf}) y plusvalía {roi_pct:+.0f}% vs compra"
        )
        return REC_ACCEPT, reasons

    # 5. Oferta claramente por encima del valor cf-base → ACEPTAR.
    if vs_market_pct is not None and vs_market_pct >= ACCEPT_OVER_MARKET_PCT:
        reasons.append(f"Oferta {vs_market_pct:+.0f}% sobre cf-base — buen momento")
        return REC_ACCEPT, reasons

    # 6. Oferta claramente baja → RECHAZAR.
    if vs_market_pct is not None and vs_market_pct <= REJECT_UNDER_MARKET_PCT:
        reasons.append(
            f"Oferta {vs_market_pct:+.0f}% bajo cf-base; aguanta o lánzalo al mercado"
        )
        return REC_REJECT, reasons

    # 7. Titular con recambio mediocre → DUDOSO, pero diciendo qué se pierde.
    # Below `XI_LOSS_REJECT` the squad survives the sale; the point of the
    # branch is that "decide según tu necesidad de cash" is unhelpful advice
    # when the size of the hole is already known.
    if is_starter and xi_loss is not None and xi_loss >= XI_LOSS_DOUBTFUL:
        reasons.append(
            f"Titular, pero con recambio: tu 11 pierde {xi_loss} SF. "
            f"Vendible si necesitas cash"
        )
        return REC_DOUBTFUL, reasons

    # 8. Proyección media con oferta razonable → DUDOSO.
    if ab.TIER_T3_MIN <= sf < ab.TIER_T2_MIN:
        if xi_loss is not None and xi_loss < XI_LOSS_DOUBTFUL:
            reasons.append(
                f"SF {sf} pero tu 11 solo pierde {xi_loss} SF sin él — "
                f"tienes recambio, vender es razonable"
            )
            return REC_DOUBTFUL, reasons
        reasons.append(f"Proyección media (SF {sf}); decide según tu necesidad de cash")
        return REC_DOUBTFUL, reasons

    # 9. Catch-all.
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


def _role_lines(s: dict) -> list[str]:
    """His role in *this* squad, and who covers the hole if he goes.

    Three facts the old single "En tu 11 actual: SÍ" could not carry, and
    whose absence is what made a first-choice goalkeeper read as sellable:
    whether he starts, what the eleven loses without him, and the name of the
    player who would take the shirt. The last one is the whole answer when
    the replacement is a substitute keeper projecting 12.
    """
    esc = lambda x: escape(str(x), quote=False)  # noqa: E731

    role = "🟢 Titular" if s["is_starter"] else "🔵 Suplente"
    lines = [f"Rol en tu plantilla: <b>{role}</b>"]

    if s.get("breaks_xi"):
        lines.append("  · ⚠️ <b>Sin recambio</b> — te quedas sin 11 legal")
        return lines

    xi_loss = s.get("xi_loss")
    if xi_loss is not None:
        lines.append(f"  · Tu 11 pierde <b>{xi_loss} SF</b> si lo vendes")
    if s.get("replacement_name"):
        rep_sf = s.get("replacement_sf")
        sf_str = f" (SF {rep_sf})" if rep_sf is not None else ""
        lines.append(f"  · Recambio: {esc(s['replacement_name'])}{esc(sf_str)}")
    return lines


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

    lines.append(f"Proyección JP: {esc(s['tier_label'])}")
    lines.extend(_role_lines(s))

    if s["until"]:
        until_dt = datetime.fromtimestamp(s["until"], MADRID_TZ)
        lines.append(f"Expira: {until_dt.strftime('%d/%m %H:%M')}")

    lines.append("")
    lines.append(f"<b>Recomendación: {rec_icon} {esc(rec)}</b>")
    for reason in s["reasons"]:
        lines.append(f"  · {esc(reason)}")

    return "\n".join(lines)
