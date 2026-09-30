"""Tests for the scraper job.

The scraper is Firestore-only now: every board message is hashed into
`comunicados/{season}/messages`, clausulazos are only ever added,
and `participacion` and `tabla_justicia` are rewritten via wipe + bulk-write. These
tests stub out Firestore and the Biwenger client so the behaviour is
exercised without touching the network or a real database.
"""

import hashlib
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.constants import MADRID_TZ
from core.domain.models import Clausulazo
from core.sdk.biwenger import board_entry_key
from packages.biwenger_tools.scraper_job.main import (
    _clausulazo_doc_id,
    _summary,
    _Tally,
    main,
)


@pytest.fixture(autouse=True)
def mock_external_deps():
    """Stub `config`, the Biwenger client, and the Firestore SDK helpers."""
    with patch(
        "packages.biwenger_tools.scraper_job.main.config",
        **{
            "BIWENGER_EMAIL": "test@example.com",
            "BIWENGER_PASSWORD": "test_password",
            "TEMPORADA_ACTUAL": "25-26",
            "LOGIN_URL": "https://fake-login",
            "ACCOUNT_URL": "https://fake-account",
            "ALL_PLAYERS_DATA_URL": "https://fake-players",
            "LEAGUE_USERS_URL": "https://fake-users",
            "CLAUSULAZOS_URL": "https://fake-clausulazos",
            "BOARD_MESSAGES_URL": "https://fake-board",
            "LEAGUE_BOARD_ALL_URL": "https://fake-board-all",
            "LEAGUE_ID": "340703",
            # Empty by default → _notify becomes a no-op in tests that
            # don't explicitly enable it. Avoids accidental real HTTP calls.
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
        },
    ), patch(
        "packages.biwenger_tools.scraper_job.main.BiwengerClient"
    ) as mock_biwenger_client, patch(
        "packages.biwenger_tools.scraper_job.main.firestore"
    ) as mock_firestore, patch(
        "packages.biwenger_tools.scraper_job.main._existing_message_ids",
        return_value=set(),
    ) as mock_existing_ids, patch(
        "packages.biwenger_tools.scraper_job.main._existing_messages",
        return_value=[],
    ) as mock_existing_msgs:

        mock_biwenger_instance = MagicMock()
        mock_biwenger_client.return_value = mock_biwenger_instance
        mock_biwenger_instance.get_all_players_data_map.return_value = {}
        mock_biwenger_instance.get_all_clausulazos.return_value = {"data": []}

        # Firestore helpers return integers; tests inspect call sites, not
        # values. Side effect on batch_write echoes the input size.
        mock_firestore.delete_collection.return_value = 0
        mock_firestore.batch_write.side_effect = lambda _coll, pairs: len(pairs)

        yield {
            "biwenger": mock_biwenger_instance,
            "firestore": mock_firestore,
            "existing_ids": mock_existing_ids,
            "existing_msgs": mock_existing_msgs,
        }


def _firestore_collections_written(mock_firestore) -> list[str]:
    return [c.args[0] for c in mock_firestore.batch_write.call_args_list]


def test_main_with_new_messages(mock_external_deps):
    """A fresh board message lands in all 4 derived collections."""
    mock_external_deps["biwenger"].get_league_users.return_value = {123: "Jorge"}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = [
        {
            "id": 1,
            "date": 1672531200,
            "author": {"id": 123},
            "title": "Un nuevo comunicado",
            "content": "Contenido del comunicado.",
        }
    ]

    main()

    # The 4 collections rewritten in the new-messages path
    assert _firestore_collections_written(mock_external_deps["firestore"]) == [
        "comunicados/25-26/messages",
        "participacion/25-26/authors",
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]
    # Every derived collection is wiped before its write; clausulazos never are
    deleted = [
        c.args[0]
        for c in mock_external_deps["firestore"].delete_collection.call_args_list
    ]
    assert deleted == [
        "comunicados/25-26/messages",
        "participacion/25-26/authors",
        "tabla_justicia/25-26/teams",
    ]

    # The new comunicado is in the messages payload (first batch_write call)
    messages_pairs = (
        mock_external_deps["firestore"].batch_write.call_args_list[0].args[1]
    )
    assert any("Un nuevo comunicado" in p[1].get("titulo", "") for p in messages_pairs)


def test_main_no_new_messages(mock_external_deps):
    """When every board message already lives in Firestore, only the
    always-written collections (clausulazos + tabla_justicia) get
    touched. Comunicados / participacion stay as-is."""
    content = "Contenido del comunicado."
    existing_hash = hashlib.sha256(f"1672531200{content}".encode("utf-8")).hexdigest()
    mock_external_deps["existing_ids"].return_value = {existing_hash}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = [
        {
            "id": 1,
            "date": 1672531200,
            "author": {"id": 123},
            "title": "Un nuevo comunicado",
            "content": content,
        }
    ]

    main()

    assert _firestore_collections_written(mock_external_deps["firestore"]) == [
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]


# --- Clausulazos are never deleted by the scraper ---


def _clause_entry(date: int, player: str, seller: str, buyer: str, amount: int):
    return {
        "date": date,
        "content": [
            {
                "type": "clause",
                "player": {"name": player},
                "from": {"name": seller},
                "to": {"name": buyer},
                "amount": amount,
            }
        ],
    }


def _feed_and_store(deps, *, stored: list, fetched: list) -> None:
    """`stored` clausulazos already in Firestore, `fetched` in Biwenger's feed."""
    deps["biwenger"].get_all_clausulazos.return_value = {"data": fetched}
    deps["firestore"].list_documents.side_effect = lambda path: (
        [(_clausulazo_doc_id(c), c.to_firestore()) for c in stored]
        if path == "clausulazos/25-26/transfers"
        else []
    )


def _batch_for(mock_firestore, collection: str) -> list:
    return next(
        c.args[1]
        for c in mock_firestore.batch_write.call_args_list
        if c.args[0] == collection
    )


_SEPTEMBER = Clausulazo("01-09-2025 10:00", "Pedri", "Lillo", "Rival", 20_000_000)
_DECEMBER_TS = 1765000000
_MAY_20 = 1747699200  # 2025-05-20, the end of 24-25


def _september_ts() -> int:
    return int(
        datetime.strptime(_SEPTEMBER.fecha, "%d-%m-%Y %H:%M")
        .replace(tzinfo=MADRID_TZ)
        .timestamp()
    )


def test_clausulazos_missing_from_the_feed_are_kept(mock_external_deps):
    """A clausulazo Biwenger stopped returning stays in Firestore."""
    _feed_and_store(
        mock_external_deps,
        stored=[_SEPTEMBER],
        fetched=[_clause_entry(_DECEMBER_TS, "Nico", "Rival", "Lillo", 9_000_000)],
    )

    main()

    fs = mock_external_deps["firestore"]
    deleted = [c.args[0] for c in fs.delete_collection.call_args_list]
    assert "clausulazos/25-26/transfers" not in deleted
    written = [doc_id for doc_id, _ in _batch_for(fs, "clausulazos/25-26/transfers")]
    assert len(written) == 1
    assert _clausulazo_doc_id(_SEPTEMBER) not in written


def test_a_renamed_team_does_not_duplicate_its_clausulazos(mock_external_deps):
    """Same date and price, new team name: the stored clausulazo, not a second one."""
    renamed = Clausulazo("01-09-2025 10:00", "Pedri", "Lillo FC", "Rival", 20_000_000)
    stored_ts = _september_ts()
    _feed_and_store(
        mock_external_deps,
        stored=[_SEPTEMBER],
        fetched=[_clause_entry(stored_ts, "Pedri", "Lillo FC", "Rival", 20_000_000)],
    )

    main()

    fs = mock_external_deps["firestore"]
    assert _clausulazo_doc_id(renamed) != _clausulazo_doc_id(_SEPTEMBER)
    assert _batch_for(fs, "clausulazos/25-26/transfers") == []
    teams = dict(_batch_for(fs, "tabla_justicia/25-26/teams"))
    assert teams["Rival"]["total_hechos"] == 1


def test_last_seasons_clausulazos_are_neither_stored_nor_missed(mock_external_deps):
    """After the rollover the feed still holds last season: none of it is written,
    counted in the justice table or reported missing."""
    _enable_notify()
    _feed_and_store(
        mock_external_deps,
        stored=[_SEPTEMBER],
        fetched=[
            _clause_entry(_MAY_20, "Nico", "Rival", "Lillo", 9_000_000),
            _clause_entry(_september_ts(), "Pedri", "Lillo", "Rival", 20_000_000),
        ],
    )

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        main()

    fs = mock_external_deps["firestore"]
    assert _batch_for(fs, "clausulazos/25-26/transfers") == []
    teams = dict(_batch_for(fs, "tabla_justicia/25-26/teams"))
    assert teams["Rival"]["total_hechos"] == 1
    assert "ya no devuelve" not in mock_send.call_args.kwargs["text"]


def test_the_justice_table_counts_stored_and_fetched_clausulazos(mock_external_deps):
    """The justice table is built from the stored clausulazos plus the feed."""
    _feed_and_store(
        mock_external_deps,
        stored=[_SEPTEMBER],
        fetched=[_clause_entry(_DECEMBER_TS, "Nico", "Lillo", "Rival", 9_000_000)],
    )

    main()

    teams = dict(
        _batch_for(mock_external_deps["firestore"], "tabla_justicia/25-26/teams")
    )
    assert teams["Rival"]["total_hechos"] == 2
    assert teams["Lillo"]["total_recibidos"] == 2


def test_clausulazos_missing_from_the_feed_are_reported(mock_external_deps):
    """Stored clausulazos the feed no longer returns: a WARNING and a Telegram line."""
    _enable_notify()
    _feed_and_store(mock_external_deps, stored=[_SEPTEMBER], fetched=[])

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send, patch("packages.biwenger_tools.scraper_job.main.logger") as log:
        main()

    assert any(
        c.kwargs.get("extra", {}).get("missing") == 1
        for c in log.warning.call_args_list
    )
    text = mock_send.call_args.kwargs["text"]
    assert "1 clausulazo que Biwenger ya no devuelve" in text


# --- The board's money entries are archived, append-only ---

_ARCHIVE = "board_archive/25-26/entries"
_JULY_10 = 1752105600  # 2025-07-10, inside 25-26
_SEASON_START = {
    "type": "seasonStarted",
    "date": _JULY_10,
    "content": {"season": {"id": 7}},
}
_TRANSFER = {
    "type": "transfer",
    "date": _JULY_10 + 1000,
    "content": [{"player": {"id": 1}, "from": {"id": 5}, "amount": 900}],
}
_CHAT = {"type": "text", "date": _JULY_10 + 500, "content": "hola"}
_LAST_SEASON = {
    "type": "market",
    "date": _JULY_10 - 500,
    "content": [{"player": {"id": 2}, "to": {"id": 5}, "amount": 100}],
}


def _board_and_archive(deps, *, board: list, archived: set) -> MagicMock:
    """`board` is the all-types read; `archived` the keys already stored."""
    deps["biwenger"].get_all_board_messages.side_effect = lambda url, **_: (
        board if url == "https://fake-board-all" else []
    )
    return patch(
        "packages.biwenger_tools.scraper_job.main._stored_ids",
        side_effect=lambda path: archived if path == _ARCHIVE else set(),
    )


def _archive_writes(mock_firestore) -> list:
    return [
        c.args[1]
        for c in mock_firestore.batch_write.call_args_list
        if c.args[0] == _ARCHIVE
    ]


def test_money_entries_are_archived_once(mock_external_deps):
    """The season's money entries are stored raw once; a second pass writes none."""
    board = [_TRANSFER, _CHAT, _SEASON_START, _LAST_SEASON]
    with _board_and_archive(mock_external_deps, board=board, archived=set()):
        main()

    (written,) = _archive_writes(mock_external_deps["firestore"])
    assert dict(written).keys() == {
        board_entry_key(_TRANSFER),
        board_entry_key(_SEASON_START),
    }
    doc = dict(written)[board_entry_key(_TRANSFER)]
    assert json.loads(doc["entry"]) == _TRANSFER
    assert (doc["type"], doc["date"]) == ("transfer", _JULY_10 + 1000)

    mock_external_deps["firestore"].batch_write.reset_mock()
    keys = {board_entry_key(_TRANSFER), board_entry_key(_SEASON_START)}
    with _board_and_archive(mock_external_deps, board=board, archived=keys):
        main()

    assert _archive_writes(mock_external_deps["firestore"]) == []


def test_the_archive_keeps_entries_the_board_lost(mock_external_deps):
    """An archived entry the board no longer returns is neither deleted nor touched."""
    lost = board_entry_key(_TRANSFER)
    with _board_and_archive(mock_external_deps, board=[_SEASON_START], archived={lost}):
        main()

    fs = mock_external_deps["firestore"]
    assert _ARCHIVE not in [c.args[0] for c in fs.delete_collection.call_args_list]
    assert all(lost not in dict(w) for w in _archive_writes(fs))


def test_a_board_read_without_its_season_start_is_archived_with_a_warning(
    mock_external_deps,
):
    """No `seasonStarted` in the read: archive what came back and say so."""
    with _board_and_archive(
        mock_external_deps, board=[_TRANSFER], archived=set()
    ), patch("packages.biwenger_tools.scraper_job.main.logger") as log:
        main()

    (written,) = _archive_writes(mock_external_deps["firestore"])
    assert dict(written).keys() == {board_entry_key(_TRANSFER)}
    assert any("seasonStarted" in c.args[0] for c in log.warning.call_args_list)


def test_the_archive_skips_last_season_after_the_rollover(mock_external_deps):
    """Season bumped before Biwenger starts it: last season's board is not archived."""
    old_start = {**_SEASON_START, "date": _MAY_20 - 9_000_000}
    old_sale = {**_TRANSFER, "date": _MAY_20}
    with _board_and_archive(
        mock_external_deps, board=[old_sale, old_start], archived=set()
    ):
        main()

    assert _archive_writes(mock_external_deps["firestore"]) == []


# --- Telegram notify on completion ---


def _enable_notify() -> None:
    """Flip the config mock so _notify actually sends."""
    from packages.biwenger_tools.scraper_job import main as scraper_main

    scraper_main.config.TELEGRAM_BOT_TOKEN = "test-token"
    scraper_main.config.TELEGRAM_CHAT_ID = "test-chat"


def test_main_sends_telegram_on_success(mock_external_deps):
    """On success, the scraper notifies the configured chat with both
    counts (messages + clausulazos)."""
    _enable_notify()
    mock_external_deps["biwenger"].get_league_users.return_value = {}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = []
    # parse_clausulazos returns nothing by default in the fixture, so the
    # count will be 0 — assert the wording reflects that.

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper OK" in text
    assert "💬 Comunicados · sin nuevos" in text
    assert "⚔️ Clausulazos · sin nuevos · 0 en total" in text
    assert "🗄️ Tablón · sin nuevos · 0 en total" in text


def test_the_summary_has_one_line_per_collection_with_its_total():
    text = _summary(
        "26-27",
        elapsed=4.2,
        messages_new=0,
        clausulazos=_Tally(new=0, total=6),
        archive=_Tally(new=253, total=253),
    )
    assert text == (
        "🧹 <b>Scraper OK</b> · 26-27 · 4s\n"
        "\n"
        "💬 Comunicados · sin nuevos\n"
        "⚔️ Clausulazos · sin nuevos · 6 en total\n"
        "🗄️ Tablón · <b>+253</b> archivados · 253 en total"
    )


def test_the_summary_counts_news_in_bold_and_singular():
    text = _summary(
        "26-27",
        elapsed=9,
        messages_new=1,
        clausulazos=_Tally(new=1, total=7, missing=1),
        archive=_Tally(new=1, total=254),
    )
    assert "💬 Comunicados · <b>+1</b> nuevo\n" in text
    assert "⚔️ Clausulazos · <b>+1</b> nuevo · 7 en total" in text
    assert "🗄️ Tablón · <b>+1</b> archivado · 254 en total" in text
    assert text.endswith(
        "\n\n⚠️ 1 clausulazo que Biwenger ya no devuelve, a salvo en Firestore"
    )


def test_main_sends_telegram_and_reraises_on_error(mock_external_deps):
    """On error, the scraper notifies AND re-raises so Cloud Run marks failed."""
    _enable_notify()
    mock_external_deps["biwenger"].get_all_board_messages.side_effect = RuntimeError(
        "biwenger 503"
    )

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        with pytest.raises(RuntimeError, match="biwenger 503"):
            main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper falló" in text
    assert "biwenger 503" in text
