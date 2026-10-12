"""Firestore persistence for the daily price snapshots the trader reads.

One document a day, `price_snapshots/{YYYY-MM-DD}`, holding every player's
cf-base price. Temporary by design: each carries `expires_at`, which the
collection's TTL policy (`infra/firestore.tf`) deletes after `TTL_DAYS`.
"""

from datetime import date, datetime, timedelta, timezone

from core.sdk import firestore as fs

COLLECTION = "price_snapshots"
TTL_DAYS = 60


def write(day: date, prices: dict[int, int]) -> None:
    """Store `day`'s prices, replacing an earlier write of the same day."""
    fs.set_document(
        COLLECTION,
        day.isoformat(),
        {
            "date": day.isoformat(),
            "prices": {str(k): v for k, v in prices.items()},
            "expires_at": datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            + timedelta(days=TTL_DAYS),
        },
    )


def recent(days: int) -> list[dict[int, int]]:
    """The last `days` snapshots, oldest first, keyed by integer player id."""
    docs = fs.query(COLLECTION, order_by="date", direction="DESCENDING", limit=days)
    return [
        {int(k): v for k, v in (d.get("prices") or {}).items()} for d in reversed(docs)
    ]
