"""Unit tests for `api/logic/public_cache` — one Biwenger read per window,
however the public taps arrive."""

import threading
import time

import pytest

from packages.biwenger_tools.api.logic import public_cache


class _FakeStore:
    """The Firestore document, in memory, with the real `state()` deciding."""

    def __init__(self, doc=None):
        self.doc = dict(doc or {})
        self.lock = threading.Lock()

    def claim(self, key, now):
        with self.lock:
            current = public_cache.state(self.doc, now)
            if current == "fresh":
                return "hit", self.doc.get("data")
            if current == "failed":
                return "failed", None
            if current == "reading":
                return "wait", None
            self.doc["lease_until"] = now + public_cache.LEASE_S
            return "claimed", None

    def write(self, key, fields):
        with self.lock:
            self.doc.update(fields)


@pytest.fixture
def store(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr(public_cache, "_claim", fake.claim)
    monkeypatch.setattr(public_cache, "_write", fake.write)
    monkeypatch.setattr(public_cache, "WAIT_STEP_S", 0.01)
    return fake


class _Counter:
    def __init__(self, value="payload", delay=0.0, fail=False):
        self.calls = 0
        self.value, self.delay, self.fail = value, delay, fail

    def __call__(self):
        self.calls += 1
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("429")
        return self.value


def test_public_league_cash_reuses_a_recent_read(store):
    read = _Counter()
    assert public_cache.get_or_read("league_cash", read) == "payload"
    assert public_cache.get_or_read("league_cash", read) == "payload"
    assert read.calls == 1


def test_a_read_cached_by_another_instance_is_reused(store):
    store.doc = {"data": "from elsewhere", "ok_at": time.time() - 10}
    read = _Counter()
    assert public_cache.get_or_read("league_cash", read) == "from elsewhere"
    assert read.calls == 0


def test_concurrent_public_taps_share_one_read(store):
    read = _Counter(delay=0.2)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(public_cache.get_or_read("k", read))
        )
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["payload", "payload"]
    assert read.calls == 1


def test_a_recent_failure_is_not_retried_by_public_taps(store):
    read = _Counter(fail=True)
    with pytest.raises(public_cache.Unavailable):
        public_cache.get_or_read("k", read)
    with pytest.raises(public_cache.Unavailable):
        public_cache.get_or_read("k", read)
    assert read.calls == 1


def test_a_fresh_payload_is_served_while_someone_refreshes_it():
    now = 1_000.0
    doc = {"data": 1, "ok_at": now - 5, "lease_until": now + 30}
    assert public_cache.state(doc, now) == "fresh"


def test_an_old_failure_and_an_expired_lease_go_stale():
    now = 1_000.0
    doc = {"failed_at": now - public_cache.FAILED_S - 1, "lease_until": now - 1}
    assert public_cache.state(doc, now) == "stale"


def test_refresh_never_raises(monkeypatch):
    def boom(key, fields):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(public_cache, "_write", boom)
    public_cache.refresh("k", {"rows": []})
