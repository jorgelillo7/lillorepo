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
        _patches("_send_image")
    ) as mock_send:
        mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
        mock_cfg.MARKET_URL = "x"

        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    assert result["sent"] == 0
    assert result["reason"] == "telegram_credentials_missing"
    mock_send.assert_not_called()
    mock_creds.assert_called_once()


def _digest_env(*, auto_bid_result=None, auto_bid_raises=None):
    """Helper: wire `run_daily`'s collaborators so only auto_bid varies."""
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
    mock_send = stack.enter_context(patch(_patches("_send_image")))
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

    mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
    mock_cfg.MARKET_URL = "x"
    return stack, mock_send, mock_auto_bid


def test_run_daily_chains_auto_bid_after_sending_images():
    """`run_daily` must call `auto_bid.run_auto_bid()` exactly once, after
    both PNGs have been sent — that's what gives the chat a clean
    squad → market → bids ordering."""
    stack, mock_send, mock_auto_bid = _digest_env(
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
    stack, mock_send, mock_auto_bid = _digest_env(
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
