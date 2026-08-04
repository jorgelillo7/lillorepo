"""Backfill `applied_at` / `waited_seconds` onto picks made before timings existed.

The draft records turn timings from the moment that feature shipped, which
leaves every earlier pick blank. Cloud Logging still holds them: each applied
transfer logged `Transfer applied.` with `player_id`, `manager_id` and `amount`,
which identify a pick uniquely.

Read-only by default. Pass `--write` to persist.

    python3 packages/biwenger_tools/scripts/biwenger_backfill_draft_timings.py \\
        --season 26-27 --freshness 72h [--write]
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone

from core.sdk import firestore as fs

LOG_FILTER = (
    'resource.type="cloud_run_revision" AND jsonPayload.message="Transfer applied."'
)


def _fetch_logs(freshness: str, limit: int) -> list:
    """Applied transfers from Cloud Logging, oldest first."""
    raw = subprocess.run(
        [
            "gcloud",
            "logging",
            "read",
            LOG_FILTER,
            f"--freshness={freshness}",
            f"--limit={limit}",
            "--format=json",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    entries = []
    for e in json.loads(raw):
        p = e.get("jsonPayload") or {}
        if not all(k in p for k in ("player_id", "manager_id", "amount")):
            continue
        entries.append(
            {
                "at": datetime.fromisoformat(
                    e["timestamp"].replace("Z", "+00:00")
                ).timestamp(),
                "player_id": int(p["player_id"]),
                "manager_id": int(p["manager_id"]),
                "amount": int(p["amount"]),
            }
        )
    return sorted(entries, key=lambda x: x["at"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--freshness", default="72h")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--write", action="store_true", help="persist (default: dry run)")
    args = ap.parse_args()

    logs = _fetch_logs(args.freshness, args.limit)
    # A reverted-then-redone pick appears twice; the last attempt is the one
    # that stuck, so later entries win.
    by_key = {(e["player_id"], e["manager_id"]): e["at"] for e in logs}

    picks_path = f"draft/{args.season}/picks"
    picks = sorted(
        (d for d in fs.query(picks_path) if d.get("status") == "applied"),
        key=lambda d: d.get("global_pick") or 0,
    )

    rows, previous_at, unmatched = [], None, []
    for pick in picks:
        at = by_key.get((int(pick["player_id"]), int(pick["manager_id"])))
        if at is None:
            unmatched.append(pick)
            previous_at = None  # the chain is broken; do not span the gap
            continue
        waited = round(at - previous_at) if previous_at is not None else None
        rows.append((pick, at, waited))
        previous_at = at

    for pick, at, waited in rows:
        when = datetime.fromtimestamp(at, timezone.utc).astimezone()
        print(
            f"{pick['global_pick']:>4}. {pick['manager_name']:<8} "
            f"{pick['player_name']:<20} {when:%d/%m %H:%M}  "
            f"espera={waited if waited is not None else '—'}"
        )
    if unmatched:
        print("\nSIN LOG (se quedan sin tiempo):")
        for pick in unmatched:
            print(f"  {pick['global_pick']:>4}. {pick['player_name']}")

    print(f"\n{len(rows)}/{len(picks)} emparejados.")
    if not args.write:
        print("Dry run — nada escrito. Repite con --write.")
        return
    for pick, at, waited in rows:
        doc_id = f"R{pick['round']:02d}P{pick['position']:02d}"
        fs.set_document(
            picks_path,
            doc_id,
            {"applied_at": at, "waited_seconds": waited, "timing_backfilled": True},
            merge=True,
        )
    # Live tracking measures each wait against `turn_started_at` on the state
    # document. Without this the first pick after the backfill has nothing to
    # measure against and lands blank.
    fs.set_document(
        f"draft/{args.season}/state",
        "current",
        {"turn_started_at": rows[-1][1]},
        merge=True,
    )
    print(f"Escritos {len(rows)} picks + turn_started_at.")


if __name__ == "__main__":
    main()
