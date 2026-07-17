"""Merge semantics of the idempotent catalog sync."""

from unittest.mock import patch

from packages.be_water.web import catalog_sync

_MOD = "packages.be_water.web.catalog_sync"

_DATASET = [
    {
        "id": "solan-de-cabras",
        "name": "Solán de Cabras",
        "province": "Cuenca",
        "community": "Castilla-La Mancha",
        "minerals": {"tds": 261},
    },
    {
        "id": "bezoya",
        "name": "Bezoya",
        "province": "Segovia",
        "community": "Castilla y León",
        "minerals": {"tds": 27},
    },
]


def _run(existing: dict):
    written: dict = {}
    with patch(f"{_MOD}.SEED_WATERS", _DATASET), patch(
        f"{_MOD}.firestore.list_documents", return_value=list(existing.items())
    ), patch(
        f"{_MOD}.firestore.set_document",
        side_effect=lambda col, doc_id, data: written.__setitem__(doc_id, data),
    ):
        summary = catalog_sync.sync_catalog()
    return summary, written


def test_creates_missing_waters():
    summary, written = _run(existing={})
    assert set(written) == {"solan-de-cabras", "bezoya"}
    assert len(summary["created"]) == 2


def test_updates_unverified_but_preserves_user_fields():
    existing = {
        "bezoya": {
            "name": "Bezoya",
            "minerals": {"tds": 99},  # stale value → dataset must win
            "verified": False,
            "photo_url": "gs://x/bezoya.jpg",  # user photo → must survive
            "added_by": "jorge",
        }
    }
    summary, written = _run(existing)
    assert "Bezoya" in summary["updated"]
    assert written["bezoya"]["minerals"]["tds"] == 27
    assert written["bezoya"]["photo_url"] == "gs://x/bezoya.jpg"
    assert written["bezoya"]["added_by"] == "jorge"


def test_never_touches_verified_waters():
    existing = {
        "bezoya": {
            "name": "Bezoya",
            "minerals": {"tds": 26.5},  # bottle-checked value
            "verified": True,
        }
    }
    summary, written = _run(existing)
    assert "bezoya" not in written
    assert "Bezoya" in summary["kept_verified"]


def test_rerun_is_a_noop(monkeypatch):
    """Second run over the freshly synced state writes nothing."""
    _, written_first = _run(existing={})
    summary, written_second = _run(existing=written_first)
    assert written_second == {}
    assert summary["unchanged"] == 2


def test_notify_skipped_without_creds(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch(f"{_MOD}.send_telegram_message") as mock_send:
        _run(existing={})
    mock_send.assert_not_called()


def test_notify_sent_with_creds(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    with patch(f"{_MOD}.send_telegram_message") as mock_send:
        _run(existing={})
    mock_send.assert_called_once()
    assert "Nuevas (2)" in mock_send.call_args.kwargs["text"]
