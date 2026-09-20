"""Unit tests for `api/logic/projection_ledger_store.py`.

Mocks Firestore at the boundary with an in-memory fake, mirroring
`test_rebuild_store.py` — the fake implements just enough of `core.sdk.
firestore`'s surface for `set_document`/`get_document`/`list_documents` to
behave like the real thing.
"""

from packages.biwenger_tools.api.logic import projection_ledger_store as store


class _FakeFirestore:
    def __init__(self):
        self.docs = {}

    def set_document(self, collection_path, doc_id, data, merge=False):
        key = (collection_path, doc_id)
        if merge and key in self.docs:
            self.docs[key] = {**self.docs[key], **data}
        else:
            self.docs[key] = dict(data)

    def get_document(self, collection_path, doc_id):
        data = self.docs.get((collection_path, doc_id))
        return dict(data) if data is not None else None

    def list_documents(self, collection_path):
        for (path, doc_id), data in self.docs.items():
            if path == collection_path:
                yield doc_id, dict(data)


def test_write_overwrites_last_seasons_snapshot_for_the_same_round(monkeypatch):
    """Only the last projection before kickoff is meant to survive — a
    second write for the same round is a forced refresh, not a merge."""
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)

    store.write({"season": "26-27", "round_id": 4901, "players": ["stale"]})
    store.write({"season": "26-27", "round_id": 4901, "players": ["fresh"]})

    assert store.read("26-27", 4901)["players"] == ["fresh"]


def test_doc_id_keys_by_season_and_round():
    assert store.doc_id("26-27", 4901) == "26-27-4901"


def test_read_returns_none_for_a_round_never_written(monkeypatch):
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)

    assert store.read("26-27", 9999) is None


def test_write_actual_merges_into_an_existing_projection(monkeypatch):
    """The grading script fills in the real outcome without disturbing the
    projection already stored for the round."""
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)
    store.write({"season": "26-27", "round_id": 4901, "has_projection": True})

    store.write_actual("26-27", 4901, {"blended_total": 46})

    doc = store.read("26-27", 4901)
    assert doc["has_projection"] is True
    assert doc["actual"] == {"blended_total": 46}


def test_write_backfill_marks_the_record_as_having_no_projection(monkeypatch):
    """A round graded before the ledger ever captured a projection for it
    must say so explicitly — it is a record with no projection, not a
    projection of zero."""
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)

    store.write_backfill(
        "26-27", 4890, "Jornada 2", "2026-09-01T09:00:00+02:00", {"blended_total": 12}
    )

    doc = store.read("26-27", 4890)
    assert doc["has_projection"] is False
    assert doc["actual"] == {"blended_total": 12}
    assert doc["round_name"] == "Jornada 2"


def test_list_all_reads_every_round_in_the_collection(monkeypatch):
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)
    store.write({"season": "26-27", "round_id": 4901})
    store.write({"season": "26-27", "round_id": 4904})

    rounds = {doc["round_id"] for doc in store.list_all()}

    assert rounds == {4901, 4904}


# --- Firestore map keys are strings; player ids are not --------------------


def test_player_points_survive_the_round_trip_as_integers():
    """`player_points` is keyed by Biwenger id, and Firestore refuses a map
    whose keys are not strings — the backfill died on exactly that. Callers
    work in ids, so the conversion belongs here rather than in each of them.
    """
    actual = {"player_points": {17021: 8, 39924: -2}, "applied_total": 6}
    stored = store._for_firestore(actual)
    assert set(stored["player_points"]) == {"17021", "39924"}
    assert store._from_firestore(stored)["player_points"] == {17021: 8, 39924: -2}


def test_a_document_without_player_points_is_left_alone():
    assert store._for_firestore({"applied_total": 3}) == {"applied_total": 3}
    assert store._from_firestore({"applied_total": 3}) == {"applied_total": 3}
