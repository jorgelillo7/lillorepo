"""Unit tests for `api/logic/rebuild_store.py`.

Mocks Firestore at the boundary with an in-memory fake rather than the real
client — the fake implements just enough of the transaction API
(`get_client`/`run_transaction`) for `claim`'s read-then-delete to behave
like the real thing.
"""

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import rebuild, rebuild_store
from packages.biwenger_tools.api.logic.lineup import DEF


class _FakeDocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self, transaction=None):
        return _FakeSnapshot(self._store.docs.get(self._key))

    def set(self, data, merge=False):
        self._store.docs[self._key] = dict(data)

    def delete(self):
        self._store.docs.pop(self._key, None)


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeTransaction:
    """A no-op wrapper: the fake doc refs already write straight to the
    shared store, exactly like the real client's transaction does once it
    commits — there is nothing here to buffer or roll back."""

    def set(self, ref, data):
        ref.set(data)

    def delete(self, ref):
        ref.delete()


class _FakeCollection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return _FakeDocRef(self._store, (self._path, doc_id))


class _FakeClient:
    def __init__(self, store):
        self._store = store

    def collection(self, path):
        return _FakeCollection(self._store, path)


class _FakeFirestore:
    """In-memory stand-in for `core.sdk.firestore`, keyed like the real
    client by `(collection_path, doc_id)`."""

    def __init__(self):
        self.docs = {}

    def set_document(self, collection_path, doc_id, data, merge=False):
        self.docs[(collection_path, doc_id)] = dict(data)

    def get_document(self, collection_path, doc_id):
        data = self.docs.get((collection_path, doc_id))
        return dict(data) if data is not None else None

    def delete_document(self, collection_path, doc_id):
        self.docs.pop((collection_path, doc_id), None)

    def delete_collection(self, collection_path, page_size=None):
        deleted = [key for key in self.docs if key[0] == collection_path]
        for key in deleted:
            del self.docs[key]
        return len(deleted)

    def get_client(self):
        return _FakeClient(self)

    def run_transaction(self, fn):
        return fn(_FakeTransaction())


def _stored_plan(clause=5_000_000):
    signing = rebuild.Signing(
        row={
            "bw_id": 1,
            "owner_user_id": 7,
            "clause_value": clause,
            "name": "X",
            "jp_player": {"predict": [{"type": 2, "rate": 300}]},
        },
        line=DEF,
        # Deliberately different from `clause_value`, to prove `store`
        # never persists this field under any name (fix for the mixed-up
        # "reserved" ceiling).
        reserve_floor=1,
    )
    return rebuild.Plan(
        signings=[signing],
        formation="3-4-3",
        completes_xi=True,
        spends_floor=False,
        total_cost=clause,
        cash_before=40_000_000,
    )


def test_store_writes_a_thin_season_scoped_document(monkeypatch):
    """The stored plan is read exactly once, by the manager's own
    confirmation tap — a candidate row's full `jp_player` payload has no
    reader there, only Firestore cost. `reserve_floor` is a planning-time
    artefact with no execution-time meaning and must never be stored."""
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    plan_id = rebuild_store.store(_stored_plan())

    path = rebuild_store._plans_path(config.CURRENT_SEASON)
    doc = fake.docs[(path, plan_id)]
    assert doc == {
        "formation": "3-4-3",
        "cash_before": 40_000_000,
        "created_at": doc["created_at"],
        "signings": [
            {
                "bw_id": 1,
                "owner_user_id": 7,
                "line": DEF,
                "clause_at_plan": 5_000_000,
                "bench": False,
            }
        ],
    }


def test_store_marks_a_bench_signing_as_such(monkeypatch):
    """Execution treats an eleven hole and a bench slot under different
    rules, so the stored document must say which is which per signing."""
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    plan = _stored_plan()
    bench_plan = rebuild.Plan(
        signings=[
            rebuild.Signing(row=plan.signings[0].row, line=DEF, reserve_floor=1),
            rebuild.Signing(
                row={**plan.signings[0].row, "bw_id": 2}, line=DEF, reserve_floor=1,
                bench=True,
            ),
        ],
        formation=plan.formation,
        completes_xi=plan.completes_xi,
        spends_floor=plan.spends_floor,
        total_cost=plan.total_cost,
        cash_before=plan.cash_before,
    )

    plan_id = rebuild_store.store(bench_plan)

    path = rebuild_store._plans_path(config.CURRENT_SEASON)
    doc = fake.docs[(path, plan_id)]
    assert [s["bench"] for s in doc["signings"]] == [False, True]


def test_storing_a_new_plan_invalidates_any_other_live_plan(monkeypatch):
    """Only one rebuild plan is ever live per season: confirming an older
    Telegram message after a newer plan replaced it must find nothing to
    execute, never a second overlapping basket for the same deficit."""
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    old_id = rebuild_store.store(_stored_plan(clause=1_000_000))
    new_id = rebuild_store.store(_stored_plan(clause=2_000_000))

    assert rebuild_store.load(old_id) is None
    assert rebuild_store.load(new_id) is not None


def test_load_reads_without_removing_the_document(monkeypatch):
    """`load` is the non-destructive read — a caller about to spend money on
    the plan must use `claim` instead, so a duplicate call never finds the
    same still-present document twice."""
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    plan_id = rebuild_store.store(_stored_plan())

    assert rebuild_store.load(plan_id)["formation"] == "3-4-3"
    assert rebuild_store.load(plan_id) is not None  # still there
    assert rebuild_store.load("does-not-exist") is None


def test_claim_removes_the_plan_so_a_second_claim_finds_nothing(monkeypatch):
    """`claim` is the atomic read-and-delete: once one caller has claimed a
    plan, every other caller for the same `plan_id` — a concurrent request,
    a crash-triggered retry, a duplicate Telegram tap — must get `None`
    before it can act on it."""
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    plan_id = rebuild_store.store(_stored_plan())

    first = rebuild_store.claim(plan_id)
    second = rebuild_store.claim(plan_id)

    assert first["formation"] == "3-4-3"
    assert second is None
    assert rebuild_store.load(plan_id) is None


def test_claim_returns_none_for_a_plan_that_was_never_stored(monkeypatch):
    fake = _FakeFirestore()
    monkeypatch.setattr(rebuild_store, "fs", fake)

    assert rebuild_store.claim("never-existed") is None
