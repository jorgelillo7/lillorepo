"""Tests for core/sdk/firestore.py.

These exercise the real Firestore client against the local emulator, so the
whole module is skipped unless ``FIRESTORE_EMULATOR_HOST`` is set. To run them:

    gcloud emulators firestore start --host-port=localhost:8080
    FIRESTORE_EMULATOR_HOST=localhost:8080 FIRESTORE_PROJECT=test-project \\
        bazel test //core:core_tests --test_output=streamed

In CI (no emulator) they skip cleanly — the SDK is a thin wrapper, and the
model-level serialization it depends on is covered by test_domain_models.py.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("FIRESTORE_EMULATOR_HOST"),
    reason="requires the Firestore emulator (set FIRESTORE_EMULATOR_HOST)",
)


@pytest.fixture
def collection():
    """A unique, empty collection path; wiped after the test."""
    from core.sdk import firestore

    os.environ.setdefault("FIRESTORE_PROJECT", "test-project")
    path = f"_it_{uuid.uuid4().hex}"
    yield path
    firestore.delete_collection(path)


def test_set_and_get_document(collection):
    from core.sdk import firestore

    firestore.set_document(collection, "doc1", {"name": "Jorge", "n": 7})
    assert firestore.get_document(collection, "doc1") == {"name": "Jorge", "n": 7}
    assert firestore.get_document(collection, "missing") is None


def test_set_document_merge(collection):
    from core.sdk import firestore

    firestore.set_document(collection, "d", {"a": 1, "b": 2})
    firestore.set_document(collection, "d", {"b": 99}, merge=True)
    assert firestore.get_document(collection, "d") == {"a": 1, "b": 99}


def test_batch_write_and_count(collection):
    from core.sdk import firestore

    docs = [(f"d{i}", {"i": i}) for i in range(1100)]  # spans the 500-op cap
    written = firestore.batch_write(collection, docs)
    assert written == 1100
    assert firestore.count(collection) == 1100


def test_list_documents(collection):
    from core.sdk import firestore

    firestore.batch_write(collection, [("a", {"v": 1}), ("b", {"v": 2})])
    got = dict(firestore.list_documents(collection))
    assert got == {"a": {"v": 1}, "b": {"v": 2}}


def test_query_filter_and_order(collection):
    from core.sdk import firestore

    firestore.batch_write(
        collection,
        [
            ("a", {"team": "X", "n": 3}),
            ("b", {"team": "X", "n": 1}),
            ("c", {"team": "Y", "n": 2}),
        ],
    )
    only_x = firestore.query(collection, "team", "==", "X", order_by="n")
    assert [d["n"] for d in only_x] == [1, 3]


def test_delete_collection(collection):
    from core.sdk import firestore

    firestore.batch_write(collection, [(f"d{i}", {"i": i}) for i in range(10)])
    deleted = firestore.delete_collection(collection)
    assert deleted == 10
    assert firestore.count(collection) == 0
