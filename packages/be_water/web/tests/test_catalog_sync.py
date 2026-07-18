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


def test_dataset_verified_flag_promotes_existing_entry():
    """A label-verified dataset entry upgrades an unverified Firestore doc,
    carrying the verified flag with it."""
    dataset = [dict(_DATASET[1], verified=True)]  # bezoya, label-checked
    existing = {"bezoya": {"name": "Bezoya", "minerals": {"tds": 99}}}
    written: dict = {}
    with patch(f"{_MOD}.SEED_WATERS", dataset), patch(
        f"{_MOD}.firestore.list_documents", return_value=list(existing.items())
    ), patch(
        f"{_MOD}.firestore.set_document",
        side_effect=lambda col, doc_id, data: written.__setitem__(doc_id, data),
    ):
        catalog_sync.sync_catalog()
    assert written["bezoya"]["verified"] is True
    assert written["bezoya"]["minerals"]["tds"] == 27


def test_verified_doc_gets_photo_enrichment_only():
    """A verified doc is data-frozen, but an empty photo_url may be filled
    from the dataset — minerals must stay exactly as bottle-checked."""
    dataset = [dict(_DATASET[1], verified=True, photo_url="https://x/bezoya.jpg")]
    existing = {
        "bezoya": {
            "name": "Bezoya",
            "minerals": {"tds": 26.5},  # bottle-checked, dataset says 27
            "verified": True,
        }
    }
    written: dict = {}
    with patch(f"{_MOD}.SEED_WATERS", dataset), patch(
        f"{_MOD}.firestore.list_documents", return_value=list(existing.items())
    ), patch(
        f"{_MOD}.firestore.set_document",
        side_effect=lambda col, doc_id, data: written.__setitem__(doc_id, data),
    ):
        catalog_sync.sync_catalog()
    assert written["bezoya"]["photo_url"] == "https://x/bezoya.jpg"
    assert written["bezoya"]["minerals"]["tds"] == 26.5  # untouched


def test_verified_doc_gets_mentions_enrichment():
    """External recognitions may land on verified docs without touching data."""
    mention = [{"source": "OCU", "label": "Excelente", "url": "https://x"}]
    dataset = [dict(_DATASET[1], verified=True, mentions=mention)]
    existing = {
        "bezoya": {"name": "Bezoya", "minerals": {"tds": 26.5}, "verified": True}
    }
    written: dict = {}
    with patch(f"{_MOD}.SEED_WATERS", dataset), patch(
        f"{_MOD}.firestore.list_documents", return_value=list(existing.items())
    ), patch(
        f"{_MOD}.firestore.set_document",
        side_effect=lambda col, doc_id, data: written.__setitem__(doc_id, data),
    ):
        catalog_sync.sync_catalog()
    assert written["bezoya"]["mentions"] == mention
    assert written["bezoya"]["minerals"]["tds"] == 26.5  # still frozen


def test_label_backed_minerals_survive_dataset_merge():
    """A mineral verified against a bottle keeps its value when the dataset
    updates an unverified doc — label beats dataset, field by field."""
    existing = {
        "bezoya": {
            "name": "Bezoya",
            "minerals": {"tds": 26.5},  # label says 26.5, dataset says 27
            "verified_fields": ["tds"],
            "verified": False,
        }
    }
    summary, written = _run(existing)
    assert written["bezoya"]["minerals"]["tds"] == 26.5
    assert "tds" in written["bezoya"]["verified_fields"]


def test_user_only_waters_are_reported_not_touched():
    """A doc the dataset doesn't know (new water or typo'd name) is surfaced
    in the summary so a human reviews it, and never written to."""
    existing = {
        "font-noba": {"name": "Font Noba", "added_by": "maria", "verified": False}
    }
    summary, written = _run(existing)
    assert summary["user_only"] == ["Font Noba (maria)"]
    assert "font-noba" not in written


def test_user_only_alone_triggers_notification(monkeypatch):
    """Even with zero dataset changes, unknown docs are worth a Telegram ping."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    _, synced = _run(existing={})  # dataset fully synced
    synced["font-noba"] = {"name": "Font Noba", "added_by": "maria"}
    with patch(f"{_MOD}.send_telegram_message") as mock_send:
        _run(existing=synced)
    mock_send.assert_called_once()
    assert "Font Noba (maria)" in mock_send.call_args.kwargs["text"]


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
