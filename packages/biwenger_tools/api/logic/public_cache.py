"""A read shared by every public caller, across Cloud Run instances.

`public_cache/{key}` holds the last good payload (`data`, `ok_at`), the last
failure (`failed_at`) and a read lease (`lease_until`). A public caller reuses
a fresh payload, waits for a read already under way instead of starting one,
and is turned away for a short while after a failure — tapping through a 429
would dig the owner's account deeper into a window the phone app shares.
"""

import time
from typing import Any, Callable

from core.sdk import firestore as fs
from core.utils import get_logger

logger = get_logger(__name__)

COLLECTION = "public_cache"
FRESH_S = 300
FAILED_S = 60
LEASE_S = 90
WAIT_STEP_S = 1.0


class Unavailable(Exception):
    """No fresh payload, and none can be read right now."""


def state(doc: dict, now: float) -> str:
    """`fresh` | `failed` | `reading` | `stale` for a cache document."""
    ok_at = doc.get("ok_at") or 0
    failed_at = doc.get("failed_at") or 0
    if ok_at and now - ok_at < FRESH_S and ok_at >= failed_at:
        return "fresh"
    if failed_at and now - failed_at < FAILED_S and failed_at > ok_at:
        return "failed"
    if (doc.get("lease_until") or 0) > now:
        return "reading"
    return "stale"


def _claim(key: str, now: float) -> tuple[str, Any]:
    """Atomically decide what this caller does: `hit` (with the payload),
    `failed`, `wait`, or `claimed` (it now holds the lease and must read)."""

    def txn(transaction):
        ref = fs.get_client().collection(COLLECTION).document(key)
        snapshot = ref.get(transaction=transaction)
        doc = snapshot.to_dict() if snapshot.exists else {}
        current = state(doc, now)
        if current == "fresh":
            return "hit", doc.get("data")
        if current == "failed":
            return "failed", None
        if current == "reading":
            return "wait", None
        transaction.set(ref, {"lease_until": now + LEASE_S}, merge=True)
        return "claimed", None

    return fs.run_transaction(txn)


def _write(key: str, fields: dict) -> None:
    fs.set_document(COLLECTION, key, fields, merge=True)


def get_or_read(
    key: str,
    read: Callable[[], Any],
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """The cached payload for `key`, reading it with `read()` only when no
    fresh one exists and nobody else is reading. Raises `Unavailable`."""
    deadline = now() + LEASE_S
    while True:
        outcome, data = _claim(key, now())
        if outcome == "hit":
            return data
        if outcome == "failed":
            raise Unavailable(key)
        if outcome == "wait":
            if now() > deadline:
                raise Unavailable(key)
            sleep(WAIT_STEP_S)
            continue
        try:
            data = read()
        except Exception as exc:
            logger.exception("Public read failed.", extra={"key": key})
            _write(key, {"failed_at": now(), "lease_until": 0})
            raise Unavailable(key) from exc
        try:
            _write(key, {"data": data, "ok_at": now(), "lease_until": 0})
        except Exception:
            # The answer was read; only its reuse is lost. The lease expires
            # on its own.
            logger.exception("Could not cache a public read.", extra={"key": key})
        return data


def refresh(key: str, data: Any, now: Callable[[], float] = time.time) -> None:
    """Store a payload read outside the cache — the owner's fresh `/saldos`.
    Never raises: the owner's answer must not depend on the cache write."""
    try:
        _write(key, {"data": data, "ok_at": now(), "lease_until": 0})
    except Exception:
        logger.exception("Could not refresh the public cache.", extra={"key": key})
