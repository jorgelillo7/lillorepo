"""Unit tests for `api/logic/digests.run_daily` — the cron orchestration.

Covers the credential-missing short-circuit, the auto-bid chaining and
its swallow-on-failure behaviour. The HTTP route is tested in
`test_routes.py`.
"""

from contextlib import ExitStack
from unittest.mock import patch


def _patches(target):
    return f"packages.biwenger_tools.api.logic.digests.{target}"


def test_run_daily_skips_send_when_telegram_creds_missing():
    with patch(_patches("config")) as mock_cfg, patch(
        _patches("check_api_health")
    ), patch(_patches("fetch_all_players"), return_value=[]), patch(
        _patches("build_jp_index"), return_value={"by_name": {}, "by_slug": {}}
    ), patch(
        _patches("BiwengerClient")
    ) as mock_client, patch(
        _patches("_send_image")
    ) as mock_send:
        mock_cfg.JP_AUTH_TOKEN = "tok"
        mock_cfg.JP_COMPETITION = 1
        mock_cfg.JP_SCORE_TYPE = 2
        mock_cfg.BIWENGER_EMAIL = "u"
        mock_cfg.BIWENGER_PASSWORD = "p"
        mock_cfg.LOGIN_URL = mock_cfg.ACCOUNT_URL = "x"
        mock_cfg.LEAGUE_ID = "1"
        mock_cfg.ALL_PLAYERS_DATA_URL = "x"
        mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
        mock_cfg.MARKET_URL = "x"
        mock_cfg.TELEGRAM_BOT_TOKEN = ""
        mock_cfg.TELEGRAM_CHAT_ID = ""
        mock_client.return_value.user_id = 1
        mock_client.return_value.get_all_players_data_map.return_value = {}

        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    assert result["sent"] == 0
    assert result["reason"] == "telegram_credentials_missing"
    mock_send.assert_not_called()


def _digest_env(*, auto_bid_result=None, auto_bid_raises=None):
    """Helper: wire `run_daily`'s collaborators so only auto_bid varies.

    Returns the entered ExitStack — the caller must close it. Designed
    for the two tests below that pin the chaining behaviour.
    """
    stack = ExitStack()
    mock_cfg = stack.enter_context(patch(_patches("config")))
    stack.enter_context(patch(_patches("check_api_health")))
    stack.enter_context(patch(_patches("fetch_all_players"), return_value=[]))
    stack.enter_context(
        patch(_patches("build_jp_index"), return_value={"by_name": {}, "by_slug": {}})
    )
    mock_client = stack.enter_context(patch(_patches("BiwengerClient")))
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

    mock_cfg.JP_AUTH_TOKEN = "tok"
    mock_cfg.JP_COMPETITION = 1
    mock_cfg.JP_SCORE_TYPE = 2
    mock_cfg.BIWENGER_EMAIL = "u"
    mock_cfg.BIWENGER_PASSWORD = "p"
    mock_cfg.LOGIN_URL = mock_cfg.ACCOUNT_URL = "x"
    mock_cfg.LEAGUE_ID = "1"
    mock_cfg.ALL_PLAYERS_DATA_URL = "x"
    mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
    mock_cfg.MARKET_URL = "x"
    mock_cfg.TELEGRAM_BOT_TOKEN = "tok"
    mock_cfg.TELEGRAM_CHAT_ID = "chat"
    mock_client.return_value.user_id = 1
    mock_client.return_value.get_all_players_data_map.return_value = {}
    mock_client.return_value.get_manager_squad.return_value = []
    mock_client.return_value.get_market_players.return_value = []
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
