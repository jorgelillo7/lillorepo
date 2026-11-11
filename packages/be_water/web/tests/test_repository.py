"""Tests for the Firestore layer's own semantics.

Every route test mocks these functions, so the whole dated-analysis series
rested on code nothing exercised: the key format, the guard that keeps an
undated composition off the timeline, and the ordering the ficha's selector
renders. A typo in the separator or a flipped sort would have shipped green.

Only `firestore` is patched — the module under test runs for real.
"""

from unittest.mock import patch

import pytest

from packages.be_water.web import repository
from packages.be_water.web.domain import Water

_FS = "packages.be_water.web.repository.firestore"


def _water(**kwargs) -> Water:
    return Water(
        id="bezoya",
        name="Bezoya",
        brand="Bezoya",
        spring="Bezoya",
        province="Segovia",
        community="Castilla y León",
        **kwargs,
    )


def test_the_entry_id_pairs_a_water_with_its_date():
    """The key *is* the replace rule: a resubmission for a date already in the
    series has to land on the same document, without a query to find it."""
    assert repository.analysis_id("bezoya", "2024-01") == "bezoya__2024-01"
    assert repository.analysis_id("bezoya", "2024") == "bezoya__2024"


def test_a_year_and_a_month_of_that_year_are_different_entries():
    """`2024` and `2024-01` are distinct analyses, not one written twice — a
    separator that collapsed them would silently overwrite a year of data."""
    assert repository.analysis_id("bezoya", "2024") != repository.analysis_id(
        "bezoya", "2024-01"
    )


def test_an_undated_composition_is_refused_rather_than_given_a_key():
    """An undated composition has no place on a timeline. Failing loudly here
    is what stops it becoming an entry keyed `bezoya__` or `bezoya__None`."""
    with patch(_FS) as fs:
        with pytest.raises(ValueError):
            repository.save_analysis(_water(minerals={"tds": 26.5}))
    fs.set_document.assert_not_called()


def test_an_entry_is_stored_under_its_own_key_with_its_own_proof():
    with patch(_FS) as fs:
        repository.save_analysis(
            _water(
                minerals={"tds": 26.5},
                verified_fields=["tds"],
                analysis_date="2024-01",
                label_photo_url="originals/bezoya__2024-01.jpg",
            )
        )
    collection, doc_id, payload = fs.set_document.call_args.args
    assert (collection, doc_id) == (repository.ANALYSES, "bezoya__2024-01")
    assert payload["minerals"] == {"tds": 26.5}
    assert payload["verified_fields"] == ["tds"]
    assert payload["label_photo_url"] == "originals/bezoya__2024-01.jpg"


def test_the_series_reads_newest_first_with_a_year_before_its_months():
    """The order the ficha's selector renders. A plain year sorts before any
    month of the same year, matching `domain.analysis_is_older`, so a `2024`
    label never displaces a `2024-06` one."""
    entries = [
        {"analysis_date": "2024"},
        {"analysis_date": "2025-02"},
        {"analysis_date": "2024-06"},
        {"analysis_date": "2021-09"},
    ]
    with patch(_FS) as fs:
        fs.query.return_value = list(entries)
        got = repository.list_analyses("bezoya")

    assert [e["analysis_date"] for e in got] == [
        "2025-02",
        "2024-06",
        "2024",
        "2021-09",
    ]


def test_the_series_asks_for_one_water_instead_of_reading_them_all():
    """Every dated ficha reads this on every view. Scanning the collection
    made one page view cost the whole catalog's history."""
    with patch(_FS) as fs:
        fs.query.return_value = []
        repository.list_analyses("bezoya")

    fs.list_documents.assert_not_called()
    assert fs.query.call_args.kwargs["value"] == "bezoya"


def test_deleting_a_water_takes_its_series_with_it():
    """Left behind, the entries reattach themselves to any water later given
    the same id — the ficha would come back with a stranger's history."""
    with patch(_FS) as fs:
        fs.query.return_value = [
            {"analysis_date": "2025-02"},
            {"analysis_date": "2024-01"},
        ]
        repository.delete_water("bezoya")

    deleted = [c.args for c in fs.delete_document.call_args_list]
    assert (repository.ANALYSES, "bezoya__2025-02") in deleted
    assert (repository.ANALYSES, "bezoya__2024-01") in deleted
    assert (repository.WATERS, "bezoya") in deleted


# --- The read cache and the daily paid-call counter ---------------------------


@pytest.fixture(autouse=True)
def _fresh_cache():
    repository.clear_cache()
    yield
    repository.clear_cache()


def _doc(water_id="bezoya"):
    return (water_id, {"name": "Bezoya", "brand": "Bezoya", "minerals": {}})


def test_the_catalogue_is_read_once_inside_the_window():
    with patch(_FS) as fs:
        fs.list_documents.return_value = [_doc()]
        first = repository.get_all_waters()
        second = repository.get_all_waters()
    assert fs.list_documents.call_count == 1
    assert [w.id for w in first] == [w.id for w in second] == ["bezoya"]


def test_callers_get_their_own_list():
    with patch(_FS) as fs:
        fs.list_documents.return_value = [_doc()]
        repository.get_all_waters().clear()
        assert len(repository.get_all_waters()) == 1


def test_the_catalogue_is_read_again_after_the_window(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(repository.time, "monotonic", lambda: clock[0])
    with patch(_FS) as fs:
        fs.list_documents.return_value = [_doc()]
        repository.get_all_waters()
        clock[0] += repository.CACHE_SECONDS - 1
        repository.get_all_waters()
        assert fs.list_documents.call_count == 1
        clock[0] += 2
        repository.get_all_waters()
        assert fs.list_documents.call_count == 2


def test_a_write_on_this_instance_drops_the_cache():
    with patch(_FS) as fs:
        fs.list_documents.return_value = [_doc()]
        repository.get_all_waters()
        repository.save_water(_water())
        repository.get_all_waters()
        assert fs.list_documents.call_count == 2


def test_the_analyses_are_cached_and_a_saved_entry_drops_them():
    with patch(_FS) as fs:
        fs.list_documents.return_value = [("a__2024", {"water_id": "a"})]
        repository.all_analyses()
        repository.all_analyses()
        assert fs.list_documents.call_count == 1
        repository.save_analysis(_water(analysis_date="2024-01", minerals={"tds": 1}))
        repository.all_analyses()
        assert fs.list_documents.call_count == 2


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _Reference:
    def __init__(self, store, doc_id):
        self.store, self.doc_id = store, doc_id

    def get(self, transaction=None):
        return _Snapshot(self.store.get(self.doc_id))


class _Transaction:
    def __init__(self, store):
        self.store = store

    def set(self, reference, data):
        self.store[reference.doc_id] = data


class _Client:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        assert name == repository.USAGE
        return type(
            "C", (), {"document": lambda _, doc_id: _Reference(self.store, doc_id)}
        )()


def _counter(store):
    def run(fn):
        return fn(_Transaction(store))

    return patch.multiple(_FS, get_client=lambda: _Client(store), run_transaction=run)


def test_paid_calls_are_counted_per_kind_and_stop_at_the_cap():
    store = {}
    with _counter(store):
        assert [repository.claim_paid_call("image", 2) for _ in range(3)] == [
            True,
            True,
            False,
        ]
        assert repository.claim_paid_call("ocr", 2) is True
    assert sorted(k.split("__")[0] for k in store) == ["image", "ocr"]
    assert next(v for k, v in store.items() if k.startswith("image"))["count"] == 2


def test_a_cap_of_zero_never_allows_a_paid_call():
    store = {}
    with _counter(store):
        assert repository.claim_paid_call("image", 0) is False
    assert store == {}


def test_when_the_counter_cannot_be_used_the_call_is_refused():
    def broken(fn):
        raise RuntimeError("firestore down")

    with patch.multiple(_FS, get_client=lambda: None, run_transaction=broken):
        assert repository.claim_paid_call("image", 5) is False
