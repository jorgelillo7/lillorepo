"""Thin Firestore CRUD helpers.

Wraps the ``google-cloud-firestore`` client with the minimal surface used
across packages (scraper writes, web reads, the one-shot backfill script).

Authentication is via Application Default Credentials:
- In Cloud Run the runtime service account is picked up automatically.
- Locally, run ``gcloud auth application-default login`` once.

No service-account key file is needed — unlike the Drive SDK in
``core/sdk/gcp.py``, which still mounts a key. That is the whole point of
moving the data layer to Firestore: ADC removes the key-file dependency.

Collection paths are passed as ``/``-joined strings, e.g.
``comunicados/25-26/messages`` (a subcollection). Firestore requires an odd
number of path segments for a collection reference; the helpers below do not
validate that — callers build the paths.
"""

import os
from typing import Iterable, Iterator, Optional

from google.cloud import firestore

from core.utils import get_logger

logger = get_logger(__name__)

# Firestore caps a single WriteBatch at 500 operations.
_BATCH_LIMIT = 500

_client: Optional[firestore.Client] = None


def get_client() -> firestore.Client:
    """Return a process-wide Firestore client, created lazily.

    The GCP project is read from ``FIRESTORE_PROJECT`` or
    ``GOOGLE_CLOUD_PROJECT`` when set; otherwise it is inferred from the
    ambient ADC credentials (the normal case inside Cloud Run).
    """
    global _client
    if _client is None:
        project = os.getenv("FIRESTORE_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        _client = firestore.Client(project=project) if project else firestore.Client()
        logger.info("Firestore client initialised.", extra={"project": _client.project})
    return _client


def get_document(collection_path: str, doc_id: str) -> Optional[dict]:
    """Return a single document as a dict, or None if it does not exist."""
    snapshot = get_client().collection(collection_path).document(doc_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def set_document(
    collection_path: str, doc_id: str, data: dict, merge: bool = False
) -> None:
    """Create or overwrite a document. With ``merge=True`` only the given
    fields are updated, leaving the rest of the document untouched."""
    get_client().collection(collection_path).document(doc_id).set(data, merge=merge)


def list_documents(collection_path: str) -> Iterator[tuple[str, dict]]:
    """Stream every document in a collection as ``(doc_id, data)`` pairs."""
    for snapshot in get_client().collection(collection_path).stream():
        yield snapshot.id, (snapshot.to_dict() or {})


def query(
    collection_path: str,
    field: Optional[str] = None,
    op: str = "==",
    value=None,
    order_by: Optional[str] = None,
    direction: str = "ASCENDING",
    limit: Optional[int] = None,
) -> list[dict]:
    """Run a simple single-clause query and return the matching documents.

    With no ``field`` this is just a (optionally ordered/limited) collection
    scan. ``direction`` is ``"ASCENDING"`` or ``"DESCENDING"``.
    """
    ref = get_client().collection(collection_path)
    if field is not None:
        ref = ref.where(filter=firestore.FieldFilter(field, op, value))
    if order_by is not None:
        ref = ref.order_by(order_by, direction=direction)
    if limit is not None:
        ref = ref.limit(limit)
    return [snapshot.to_dict() or {} for snapshot in ref.stream()]


def count(collection_path: str) -> int:
    """Return the document count of a collection via an aggregation query.

    Aggregation counts are billed as a tiny fixed number of reads regardless
    of collection size — cheap, and well inside the free tier. Used by the
    backfill script to verify parity with the source CSVs.
    """
    result = get_client().collection(collection_path).count().get()
    # The client returns a list of AggregationResult rows.
    return int(result[0][0].value)


def batch_write(collection_path: str, docs: Iterable[tuple[str, dict]]) -> int:
    """Bulk-write ``(doc_id, data)`` pairs, chunked under the 500-op batch cap.

    Each write is a ``set`` (full overwrite), so re-running with the same doc
    ids is idempotent. Returns the number of documents written.
    """
    client = get_client()
    collection = client.collection(collection_path)
    written = 0
    batch = client.batch()
    pending = 0
    for doc_id, data in docs:
        batch.set(collection.document(doc_id), data)
        pending += 1
        written += 1
        if pending >= _BATCH_LIMIT:
            batch.commit()
            batch = client.batch()
            pending = 0
    if pending:
        batch.commit()
    logger.info(
        "Batch write committed.",
        extra={"collection": collection_path, "count": written},
    )
    return written


def delete_collection(collection_path: str, page_size: int = _BATCH_LIMIT) -> int:
    """Delete every document in a collection. Returns the number deleted.

    Used by tests and to make the backfill safely re-runnable. Note this does
    not recurse into subcollections — Firestore keeps those independent.
    """
    client = get_client()
    collection = client.collection(collection_path)
    deleted = 0
    while True:
        snapshots = list(collection.limit(page_size).stream())
        if not snapshots:
            break
        batch = client.batch()
        for snapshot in snapshots:
            batch.delete(snapshot.reference)
        batch.commit()
        deleted += len(snapshots)
        if len(snapshots) < page_size:
            break
    return deleted
