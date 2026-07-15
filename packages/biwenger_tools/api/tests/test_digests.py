"""Unit tests for `api/logic/digests.run_daily` — the cron orchestration.

Covers the credential-missing short-circuit, the auto-bid chaining and
its swallow-on-failure behaviour. The HTTP route is tested in
`test_routes.py`.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch


def _patches(target):
    return f"packages.biwenger_tools.api.logic.digests.{target}"


def _build_ctx(biwenger):
    """Wrap a Biwenger mock in an OrchestratorContext for `build_context` to
    return. Pulled out so every test stays on the same wiring."""
    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    return OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={},
        jp_index={"by_name": {}, "by_slug": {}},
    )


def test_run_daily_skips_send_when_telegram_creds_missing():
    biwenger = MagicMock()
    biwenger.user_id = 1
    with patch(_patches("config")) as mock_cfg, patch(
        _patches("build_context"), return_value=_build_ctx(biwenger)
    ), patch(_patches("require_telegram"), return_value=None) as mock_creds, patch(
        _patches("send_image_or_text_fallback")
    ) as mock_send:
        mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
        mock_cfg.MARKET_URL = "x"

        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    assert result["sent"] == 0
    assert result["reason"] == "telegram_credentials_missing"
    mock_send.assert_not_called()
    mock_creds.assert_called_once()


def _digest_env(
    *,
    auto_bid_result=None,
    auto_bid_raises=None,
    offers_result=None,
    offers_raises=None,
    paused_until="",
):
    """Helper: wire `run_daily`'s collaborators so only the varying step changes."""
    stack = ExitStack()
    mock_cfg = stack.enter_context(patch(_patches("config")))
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_manager_squad.return_value = []
    biwenger.get_market_players.return_value = []
    stack.enter_context(
        patch(_patches("build_context"), return_value=_build_ctx(biwenger))
    )
    # `require_telegram` reads orchestration.config — patch the helper itself
    # to dodge the cross-module config indirection.
    stack.enter_context(
        patch(_patches("require_telegram"), return_value=("tok", "chat"))
    )
    mock_send = stack.enter_context(
        patch(_patches("send_image_or_text_fallback"), return_value=True)
    )
    # `build_table_image` runs synchronously before `_send_image` — patching
    # the renderer avoids matplotlib choking on the empty-row stub data.
    stack.enter_context(patch(_patches("build_table_image"), return_value=b""))
    if auto_bid_raises is not None:
        mock_auto_bid = stack.enter_context(
            patch(_patches("auto_bid.run_auto_bid"), side_effect=auto_bid_raises)
        )
    else:
        mock_auto_bid = stack.enter_context(
            patch(_patches("auto_bid.run_auto_bid"), return_value=auto_bid_result or {})
        )

    # The offers inbox step. Default: silent (empty inbox).
    if offers_raises is not None:
        mock_offers = stack.enter_context(
            patch(_patches("offers.run_offers_inbox"), side_effect=offers_raises)
        )
    else:
        mock_offers = stack.enter_context(
            patch(
                _patches("offers.run_offers_inbox"),
                return_value=offers_result or {"sent": 0, "offers": 0},
            )
        )

    mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
    mock_cfg.MARKET_URL = "x"
    mock_cfg.AUTO_BID_PAUSED_UNTIL = paused_until
    return stack, mock_send, mock_auto_bid, mock_offers


def test_run_daily_chains_auto_bid_after_sending_images():
    """`run_daily` must call `auto_bid.run_auto_bid()` exactly once, after
    both PNGs have been sent — that's what gives the chat a clean
    squad → market → bids ordering."""
    stack, mock_send, mock_auto_bid, _ = _digest_env(
        auto_bid_result={"bid_count": 2, "skipped_count": 3, "total_bid_eur": 4_000_000}
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    # 2 image sends happened first (my team + market).
    assert mock_send.call_count == 2
    assert result["sent"] == 2
    assert result["auto_bid"]["bid_count"] == 2


def test_run_daily_swallows_auto_bid_failure_and_still_returns_digest_summary():
    """A broken auto-bid run must not lose the digest we already sent. The
    summary surfaces the error, but the route stays 200 OK."""
    stack, mock_send, mock_auto_bid, _ = _digest_env(
        auto_bid_raises=RuntimeError("biwenger 503")
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    assert mock_send.call_count == 2
    assert result["sent"] == 2
    assert "error" in result["auto_bid"]
    assert "biwenger 503" in result["auto_bid"]["error"]


def test_run_daily_continues_to_auto_bid_when_first_photo_fails():
    """Regression for 22–23/06/2026 incidents: sendPhoto stalled past the
    gunicorn timeout, the digest died at the first image, and auto-bid
    never ran. The fix: photo failure is now caught per-image, replaced
    by a text fallback, and the rest of the digest (mercado + auto-bid)
    continues to run."""
    stack, mock_send, mock_auto_bid, _ = _digest_env(
        auto_bid_result={"bid_count": 1, "skipped_count": 0, "total_bid_eur": 1_000_000}
    )
    mock_send.return_value = False  # both photos fail
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    assert mock_send.call_count == 2
    mock_auto_bid.assert_called_once()
    assert result["sent"] == 0
    assert result["auto_bid"]["bid_count"] == 1


def test_send_image_or_text_fallback_sends_text_on_telegram_delivery_error():
    """When `sendPhoto` raises, the helper must post a text fallback so the
    user still sees the section landed even if Telegram refused the image."""
    from core.sdk.telegram import TelegramDeliveryError
    from packages.biwenger_tools.api.logic import orchestration

    orch = "packages.biwenger_tools.api.logic.orchestration."
    with patch(
        orch + "send_telegram_photo_or_raise",
        side_effect=TelegramDeliveryError("boom"),
    ), patch(orch + "send_telegram_message") as mock_text, patch(orch + "time.sleep"):
        ok = orchestration.send_image_or_text_fallback(
            "tok", "chat", b"img", "Mi equipo"
        )

    assert ok is False
    mock_text.assert_called_once()
    text = mock_text.call_args.kwargs.get("text", "")
    assert "Mi equipo" in text
    assert "no salió" in text


def test_run_daily_notifies_telegram_when_inner_raises():
    """A top-level failure (e.g. Biwenger 5xx during build_context) must
    surface a Telegram message before propagating, so the user doesn't
    suffer silent failures like the 22–23/06 incidents."""
    from packages.biwenger_tools.api.logic import digests

    with patch(
        _patches("_run_daily_inner"), side_effect=RuntimeError("biwenger 503")
    ), patch(_patches("require_telegram"), return_value=("tok", "chat")), patch(
        _patches("send_telegram_message")
    ) as mock_send:
        try:
            digests.run_daily()
        except RuntimeError:
            pass

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Digest diario falló" in text
    assert "biwenger 503" in text


# --- section resilience -----------------------------------------------------


def test_run_daily_market_survives_team_section_failure():
    """A broken "Mi equipo" section (fetch, rows or render) must not kill
    the market image nor the auto-bid step — the chat gets a short
    failure note for the dead section and the digest continues."""

    def _boom_on_team(rows, title, extra_cols=None):
        if title == "Mi equipo":
            raise RuntimeError("render boom")
        return b""

    stack, mock_send, mock_auto_bid, _ = _digest_env(
        auto_bid_result={"bid_count": 0, "skipped_count": 0}
    )
    stack.enter_context(patch(_patches("build_table_image"), side_effect=_boom_on_team))
    mock_text = stack.enter_context(patch(_patches("send_telegram_message")))
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    # Only the market image went out; the team section degraded to a note.
    assert mock_send.call_count == 1
    assert mock_send.call_args.args[3] == "Mercado"
    mock_auto_bid.assert_called_once()
    assert result["sent"] == 1
    note = mock_text.call_args.kwargs.get("text", "")
    assert "Mi equipo" in note


# --- auto-bid pause ----------------------------------------------------------


def test_run_daily_skips_auto_bid_while_paused():
    """While today < AUTO_BID_PAUSED_UNTIL the digest must not bid; it posts
    a pause note instead and the summary carries the resume date."""
    stack, mock_send, mock_auto_bid, mock_offers = _digest_env(
        paused_until="2999-01-01"
    )
    mock_text = stack.enter_context(patch(_patches("send_telegram_message")))
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_not_called()
    mock_offers.assert_called_once()  # offers analysis stays active
    assert mock_send.call_count == 2  # team + market images still sent
    assert result["auto_bid"] == {"paused_until": "2999-01-01"}
    note = mock_text.call_args.kwargs.get("text", "")
    assert "pausadas" in note
    assert "/pujar" in note


def test_run_daily_runs_auto_bid_once_pause_expired():
    """A past AUTO_BID_PAUSED_UNTIL re-enables bidding with no deploy."""
    stack, _, mock_auto_bid, _ = _digest_env(
        paused_until="2000-01-01", auto_bid_result={"bid_count": 1}
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    assert result["auto_bid"]["bid_count"] == 1


def test_run_daily_ignores_malformed_pause_date():
    """A typo in AUTO_BID_PAUSED_UNTIL must never disable bidding."""
    stack, _, mock_auto_bid, _ = _digest_env(
        paused_until="septiembre", auto_bid_result={"bid_count": 0}
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()


# --- offers inbox chained at the end --------------------------------------


def test_run_daily_chains_offers_inbox_after_auto_bid():
    """The offers step runs after auto-bid and its result is surfaced in
    the returned summary."""
    stack, _, mock_auto_bid, mock_offers = _digest_env(
        offers_result={"sent": 2, "offers": 2}
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    mock_offers.assert_called_once()
    assert result["offers"] == {"sent": 2, "offers": 2}


def test_run_daily_swallows_offers_inbox_failure():
    """A blown offers step must not break the digest — the auto-bid summary
    is already delivered."""
    stack, _, mock_auto_bid, mock_offers = _digest_env(
        offers_raises=RuntimeError("offers boom")
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    mock_offers.assert_called_once()
    assert "error" in result["offers"]
    assert "offers boom" in result["offers"]["error"]
