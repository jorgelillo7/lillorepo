"""Daily digest — "my team + market + lineup + auto-bid + offers to accept" to Telegram.

Used by `POST /digests/daily`, which Cloud Scheduler hits once a day. The
chain (squad → market → lineup → bids → offers) is fired in this order so the
user gets a coherent morning briefing in guaranteed sequence, instead of
multiple independent Scheduler jobs racing.

Every step is wrapped in a swallow-on-failure helper so one failing step
doesn't lose the rest of the digest.

The lineup step exists so a player who arrives overnight is fielded without
anyone opening the app. It runs at 09:00 like everything else, which is early:
Biwenger locks each player at *his* kickoff, and a matchday can span days, so
this is a floor and not the best possible lineup.

One fixed hour is chosen over waking near each kickoff on purpose. The precise
version needs a tick that reads the fixture list and self-gates, and the gain
over "a decent lineup every morning, forced by hand before a match that
matters" does not pay for it. What the floor buys is that forgetting costs a
stale lineup instead of an empty one.

The auto-bid step honours `config.AUTO_BID_PAUSED_UNTIL`: while today
(Madrid) is before that date the digest skips it and posts a short pause
note instead. The manual `POST /market/auto-bid` endpoint is not affected.
"""

from datetime import date, datetime

from core.constants import MADRID_TZ
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    actions,
    auto_bid,
    fixture_run,
    offers,
    provider_watch,
)
from packages.biwenger_tools.api.logic.image_formatter import build_table_image
from packages.biwenger_tools.api.logic.orchestration import (
    build_context,
    require_telegram,
    send_image_or_text_fallback,
)
from packages.biwenger_tools.api.logic.rows import build_market_rows, build_squad_rows

logger = get_logger(__name__)


def _auto_bid_pause_active() -> bool:
    """True while today (Madrid) is before `config.AUTO_BID_PAUSED_UNTIL`.

    An empty or malformed value means "not paused" — a config typo must
    never silently disable bidding forever.
    """
    raw = (config.AUTO_BID_PAUSED_UNTIL or "").strip()
    if not raw:
        return False
    try:
        resume = date.fromisoformat(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid AUTO_BID_PAUSED_UNTIL %r — ignoring pause.", raw)
        return False
    return datetime.now(MADRID_TZ).date() < resume


def _notify_auto_bid_paused(token: str, chat_id: str) -> None:
    """One-liner so the pause is visible in the chat and not read as a failure."""
    resume = date.fromisoformat(config.AUTO_BID_PAUSED_UNTIL.strip())
    send_telegram_message(
        bot_token=token,
        chat_id=chat_id,
        text=(
            f"⏸️ Pujas automáticas pausadas hasta el {resume.strftime('%d/%m/%Y')}. "
            "Puedes lanzarlas a mano con /pujar."
        ),
    )


def _observed_market_rows(
    biwenger,
    market_players,
    biwenger_players,
    jp_index,
    oraculo_index=None,
    oraculo_scale=None,
):
    """Market rows, watched on the way past.

    `provider_watch.observe` used to see only the squad — about twenty players
    — while the disagreement rate it cites was measured across the whole league
    payload. That is roughly one sighting per two dozen lineups, which is why
    two backlog items had twelve months of silence to read.

    These rows are built every morning either way, so watching them costs no
    extra Biwenger call. The observer decides nothing; a failure here must not
    cost the digest its market section, which is the section most likely to be
    empty already.
    """
    rows = build_market_rows(
        market_players,
        biwenger_players,
        jp_index,
        oraculo_index,
        oraculo_scale=oraculo_scale,
    )
    try:
        provider_watch.observe(rows)
    except Exception:  # pragma: no cover - an observer must never break a send
        logger.warning("Market observation failed; digest unaffected.", exc_info=True)
    return rows


def _safe_send_section(
    token: str,
    chat_id: str,
    build_rows,
    title: str,
    show_total_value: bool = False,
    extra_cols: list[str] | None = None,
):
    """Build and send one digest table; never raises.

    Returns `(image_sent, row_count)`. On any failure (Biwenger fetch,
    row building, rendering) it logs, posts a short text note so the
    chat shows the section died, and lets the digest continue — the
    remaining sections must still arrive.
    """
    try:
        rows = build_rows()
        sent = send_image_or_text_fallback(
            token,
            chat_id,
            build_table_image(
                rows, title, show_total_value=show_total_value, extra_cols=extra_cols
            ),
            title,
        )
        return sent, len(rows)
    except Exception:
        logger.exception("Digest section failed.", extra={"section": title})
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                f"⚠️ <b>{title}</b> no pudo generarse hoy. "
                "Continúo con el resto del digest."
            ),
        )
        return False, 0


def _safe_run_auto_bid() -> dict:
    """Run auto-bid but never raise — the digest above already shipped."""
    try:
        return auto_bid.run_auto_bid()
    except Exception as exc:
        logger.exception("Auto-bid step failed inside daily digest.")
        return {"error": str(exc)}


def _safe_run_auto_pick(ctx) -> dict:
    """Set the lineup but never raise. Reuses the digest's ctx so the step
    costs no second JP + Biwenger round-trip."""
    if not config.DAILY_LINEUP_ENABLED:
        return {"skipped": "disabled"}
    try:
        return actions.run_auto_pick_lineup(ctx=ctx)
    except Exception as exc:
        logger.exception("Lineup step failed inside daily digest.")
        return {"error": str(exc)}


def _notify_step_failed(token: str, chat_id: str, title: str) -> None:
    """Tell the chat a step died, best effort.

    Swallows its own failure: if Telegram is what broke, there is nothing
    left to say it with, and the digest must still finish.
    """
    try:
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                f"⚠️ <b>{title}</b> no pudo generarse hoy. "
                "Continúo con el resto del digest."
            ),
        )
    except Exception:  # pragma: no cover - nothing left to report with
        logger.exception("Could not notify a failed digest step.")


def _safe_run_protection_watch(ctx) -> dict:
    """Warn about clause protection ending on one of my players. Never raises:
    a board or squad read failing must not cost the offers step after it."""
    try:
        return actions.run_protection_watch(ctx)
    except Exception as exc:
        logger.exception("Protection watch failed inside daily digest.")
        return {"error": str(exc)}


def _safe_run_offers_inbox(ctx) -> dict:
    """Run the offers inbox step but never raise. Reuses the digest's ctx
    so we don't pay a second JP+Biwenger round-trip. Accept-only: the morning
    interrupts for an offer worth taking; `/ofertas` shows every one."""
    try:
        return offers.run_offers_inbox(ctx, only_accept=True)
    except Exception as exc:
        logger.exception("Offers inbox step failed inside daily digest.")
        return {"error": str(exc)}


def _notify_digest_failure(exc: Exception) -> None:
    """Best-effort error notification when `run_daily` blows up.

    Run after the digest's own try/except so the user gets at least a
    "today's batch failed because X" message instead of silence. The send
    itself swallows exceptions — if Telegram is the source of the failure
    there is nothing more we can do.
    """
    telegram = require_telegram()
    if telegram is None:
        return
    token, chat_id = telegram
    try:
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                "🚨 <b>Digest diario falló</b>\n"
                f"<code>{type(exc).__name__}: {exc}</code>\n"
                "Las pujas automáticas pueden no haberse ejecutado."
            ),
        )
    except Exception:
        logger.exception("Failed to notify Telegram of digest failure.")


def run_daily() -> dict:
    """Send my squad + market images, then chain the auto-bid summary.

    Side effects: hits JP, hits Biwenger, sets the lineup, sends 2 PNGs +
    2 text messages to Telegram (lineup + auto-bid). Top-level errors are surfaced
    to Telegram before propagating so the user never gets silent
    failures like the 22/06–23/06 incidents.
    """
    try:
        return _run_daily_inner()
    except Exception as exc:
        _notify_digest_failure(exc)
        raise


def _run_daily_inner() -> dict:
    ctx = build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    upcoming = actions.read_fixture_runs(ctx.biwenger)
    fixture_column = fixture_run.column_for(upcoming)

    def _team_rows():
        my_squad = ctx.biwenger.get_manager_squad(
            config.USER_SQUAD_URL, ctx.biwenger.user_id
        )
        rows = build_squad_rows(
            my_squad,
            ctx.biwenger_players,
            ctx.jp_index,
            ctx.oraculo_index,
            oraculo_scale=ctx.oraculo_scale,
        )
        fixture_run.annotate(rows, upcoming)
        return rows

    def _market_rows():
        market_players = ctx.biwenger.get_market_players(config.MARKET_URL)
        rows = _observed_market_rows(
            ctx.biwenger,
            market_players,
            ctx.biwenger_players,
            ctx.jp_index,
            ctx.oraculo_index,
            oraculo_scale=ctx.oraculo_scale,
        )
        fixture_run.annotate(rows, upcoming)
        return rows

    team_sent, team_count = _safe_send_section(
        token,
        chat_id,
        _team_rows,
        "Mi equipo",
        show_total_value=True,
        extra_cols=[fixture_column],
    )
    market_sent, market_count = _safe_send_section(
        token, chat_id, _market_rows, "Mercado", extra_cols=[fixture_column]
    )

    lineup_result = _safe_run_auto_pick(ctx)

    if _auto_bid_pause_active():
        _notify_auto_bid_paused(token, chat_id)
        auto_bid_result = {"paused_until": config.AUTO_BID_PAUSED_UNTIL}
    else:
        auto_bid_result = _safe_run_auto_bid()
    protection_result = _safe_run_protection_watch(ctx)
    offers_result = _safe_run_offers_inbox(ctx)

    sent_count = int(team_sent) + int(market_sent)
    logger.info(
        "Daily analysis sent.",
        extra={
            "my_team": team_count,
            "market": market_count,
            "images_sent": sent_count,
            "lineup_applied": lineup_result.get("applied"),
            "auto_bid_placed": auto_bid_result.get("bid_count"),
            "auto_bid_skipped": auto_bid_result.get("skipped_count"),
            "offers_inbox": offers_result.get("offers"),
            "offers_sent": offers_result.get("sent"),
        },
    )
    return {
        "sent": sent_count,
        "my_team": team_count,
        "market": market_count,
        "lineup": lineup_result,
        "auto_bid": auto_bid_result,
        "protection": protection_result,
        "offers": offers_result,
    }
