"""Tests for `price_history_store`: one Firestore document of prices a day."""

from datetime import date, datetime, timedelta, timezone

from packages.biwenger_tools.api.logic import price_history_store as store


class _FakeFirestore:
    def __init__(self):
        self.docs = {}

    def set_document(self, collection_path, doc_id, data, merge=False):
        self.docs[(collection_path, doc_id)] = dict(data)

    def query(self, collection_path, order_by=None, direction="ASCENDING", limit=None):
        rows = [d for (path, _), d in self.docs.items() if path == collection_path]
        rows.sort(key=lambda d: d[order_by], reverse=direction == "DESCENDING")
        return [dict(d) for d in rows[:limit]]


def test_a_day_is_stored_once_under_its_date_with_an_expiry(monkeypatch):
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)

    store.write(date(2026, 10, 12), {7: 2_000_000})
    store.write(date(2026, 10, 12), {7: 2_100_000})

    doc = fake.docs[(store.COLLECTION, "2026-10-12")]
    assert doc["prices"] == {"7": 2_100_000}
    assert doc["expires_at"] == datetime(2026, 10, 12, tzinfo=timezone.utc) + timedelta(
        days=store.TTL_DAYS
    )


def test_recent_returns_the_last_days_oldest_first_with_integer_ids(monkeypatch):
    fake = _FakeFirestore()
    monkeypatch.setattr(store, "fs", fake)
    for day, price in ((10, 1), (11, 2), (12, 3)):
        store.write(date(2026, 10, day), {7: price})

    assert store.recent(2) == [{7: 2}, {7: 3}]
