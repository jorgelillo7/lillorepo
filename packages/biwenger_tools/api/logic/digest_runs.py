"""One daily digest per Madrid day, across instances and duplicate deliveries.

Cloud Scheduler delivers at least once: the same tick can reach the service
twice, seconds apart, on two instances. `digest_runs/{day}` records the run
(`status`, `started_at`, `finished_at`) and a transaction lets only one caller
start it. A failed run may be retried, and one that never finished (an
instance killed mid-run) stops blocking after `STALE_S`.
"""

from core.sdk import firestore as fs

COLLECTION = "digest_runs"
STALE_S = 900


def may_start(doc: dict, now: float) -> bool:
    """Whether a run may start, given the day's document (empty if none)."""
    status = doc.get("status")
    if status == "done":
        return False
    if status == "running":
        return now - (doc.get("started_at") or 0) >= STALE_S
    return True


def claim(day: str, now: float) -> bool:
    """Atomically take the day. False means another delivery already has it."""

    def txn(transaction):
        ref = fs.get_client().collection(COLLECTION).document(day)
        snapshot = ref.get(transaction=transaction)
        if not may_start(snapshot.to_dict() if snapshot.exists else {}, now):
            return False
        transaction.set(ref, {"status": "running", "started_at": now})
        return True

    return fs.run_transaction(txn)


def finish(day: str, *, ok: bool, now: float) -> None:
    """Close the day's run: `done` blocks the day, `failed` leaves it open."""
    fs.set_document(
        COLLECTION,
        day,
        {"status": "done" if ok else "failed", "finished_at": now},
        merge=True,
    )
