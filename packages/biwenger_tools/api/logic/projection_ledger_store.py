"""Firestore persistence for the projection ledger.

Mirrors `rebuild_store` for `rebuild.py`: `projection_ledger.py` stays pure
(no I/O); this module owns the one collection the daily snapshot and the
grading/backfill script both need, one document per round.
"""

from typing import Optional

from core.sdk import firestore as fs

COLLECTION = "proyecciones"


def doc_id(season: str, round_id: int) -> str:
    return f"{season}-{round_id}"


def write(snapshot: dict) -> None:
    """Overwrite the round's document with this morning's snapshot.

    A plain `set`, not a merge: the ledger's own scheduling rule
    (`projection_ledger.target_round`) is that only the last projection
    before the round's kickoff survives, so today's read replacing
    yesterday's is the intended behaviour, not data loss.
    """
    fs.set_document(
        COLLECTION, doc_id(snapshot["season"], snapshot["round_id"]), snapshot
    )


def read(season: str, round_id: int) -> Optional[dict]:
    return fs.get_document(COLLECTION, doc_id(season, round_id))


def write_actual(season: str, round_id: int, actual: dict) -> None:
    """Merge a round's real outcome into whatever document already exists —
    a projection snapshot gaining its comparison, or a `write_backfill`
    record gaining the outcome it was seeded for."""
    fs.set_document(
        COLLECTION, doc_id(season, round_id), {"actual": actual}, merge=True
    )


def write_backfill(
    season: str, round_id: int, round_name: str | None, captured_at: str, actual: dict
) -> None:
    """A record for a round that finished before the ledger ever captured a
    projection for it. `has_projection: False` says so explicitly — this must
    never be mistaken for a projection of zero."""
    fs.set_document(
        COLLECTION,
        doc_id(season, round_id),
        {
            "season": season,
            "round_id": round_id,
            "round_name": round_name,
            "captured_at": captured_at,
            "has_projection": False,
            "actual": actual,
        },
    )


def list_all() -> list:
    """Every round's document, for the grading script to walk."""
    return [data for _, data in fs.list_documents(COLLECTION)]
