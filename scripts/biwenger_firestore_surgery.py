#!/usr/bin/env python3
"""Surgical Firestore edits for scraper recovery scenarios.

Three subcommands, all dry-run by default; pass ``--apply`` to write:

``list-messages <SEASON> [--author X] [--limit N]``
    Print message docs in ``comunicados/{SEASON}/messages`` for inspection
    (id, fecha, autor, titulo). Use it to find the ``doc-id`` for a
    subsequent ``move-message``.

``move-message <FROM> <TO> --doc-id <ID> [--rename-author <NAME>]``
    Copy a single message from ``comunicados/{FROM}`` to
    ``comunicados/{TO}`` (same doc id — the id_hash is content-derived,
    so renaming the author does not change it). Then add the doc id to
    the destination ``participacion/{TO}/authors/{autor}`` bucket that
    matches the message ``categoria``. Idempotent.

``wipe-season <SEASON>``
    Delete every document under the four scraper-produced subcollections
    for the season:
        comunicados/{SEASON}/messages
        participacion/{SEASON}/authors
        clausulazos/{SEASON}/transfers
        tabla_justicia/{SEASON}/teams
    Use when a scrape ran against the wrong season.

Examples::

    # Find the message id by scanning the bad-season collection
    python3 scripts/biwenger_firestore_surgery.py list-messages 26-27 --limit 5

    # Move it to the right season, renaming the author to the season-1 team name
    python3 scripts/biwenger_firestore_surgery.py move-message 26-27 25-26 \\
        --doc-id <hash> --rename-author 'Los caídos de la jornada' --apply

    # Wipe everything the scraper wrote under the wrong season
    python3 scripts/biwenger_firestore_surgery.py wipe-season 26-27 --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.domain.models import Participation  # noqa: E402
from core.sdk.firestore import get_client  # noqa: E402

_CATEGORY_BUCKET = {
    "comunicado": "comunicados",
    "dato": "datos",
    "cesion": "cesiones",
    "cronica": "cronicas",
}

_SCRAPER_SUBCOLLECTIONS = (
    "comunicados/{s}/messages",
    "participacion/{s}/authors",
    "clausulazos/{s}/transfers",
    "tabla_justicia/{s}/teams",
)


def _cmd_list_messages(args) -> None:
    client = get_client()
    coll = client.collection(f"comunicados/{args.season}/messages")
    rows = []
    for snap in coll.stream():
        data = snap.to_dict() or {}
        if args.author and data.get("autor") != args.author:
            continue
        rows.append((snap.id, data))
    rows.sort(key=lambda r: str(r[1].get("fecha", "")), reverse=True)
    if args.limit:
        rows = rows[: args.limit]

    print(f"{len(rows)} message(s) in comunicados/{args.season}/messages:\n")
    for doc_id, data in rows:
        print(f"  id     : {doc_id}")
        print(f"  fecha  : {data.get('fecha', '')}")
        print(f"  autor  : {data.get('autor', '')}")
        print(f"  titulo : {data.get('titulo', '')}")
        print(f"  cat    : {data.get('categoria', '')}")
        print()


def _cmd_move_message(args) -> None:
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"[{mode}] Move {args.doc_id[:12]}… "
        f"comunicados/{args.from_season} → comunicados/{args.to_season}"
    )

    client = get_client()
    src_ref = (
        client.collection(f"comunicados/{args.from_season}/messages")
        .document(args.doc_id)
    )
    src_snap = src_ref.get()
    if not src_snap.exists:
        print(
            f"ERROR: source doc not found at "
            f"comunicados/{args.from_season}/messages/{args.doc_id}",
            file=sys.stderr,
        )
        sys.exit(1)

    src_data = src_snap.to_dict() or {}
    original_autor = src_data.get("autor", "")
    new_autor = args.rename_author or original_autor
    target_data = dict(src_data)
    if args.rename_author:
        target_data["autor"] = args.rename_author

    print("\nSource doc:")
    for k in ("fecha", "autor", "titulo", "categoria"):
        print(f"  {k:8s}: {src_data.get(k, '')}")
    if args.rename_author:
        print(f"\nRename autor: {original_autor!r} → {new_autor!r}")

    # --- Participation update planning ---
    bucket_name = _CATEGORY_BUCKET.get(target_data.get("categoria", ""))
    if not bucket_name:
        print(
            f"\nWARNING: unknown categoria {target_data.get('categoria')!r}; "
            "participation will NOT be updated. Move continues.",
            file=sys.stderr,
        )
    else:
        part_ref = (
            client.collection(f"participacion/{args.to_season}/authors")
            .document(new_autor)
        )
        part_snap = part_ref.get()
        if part_snap.exists:
            part_data = part_snap.to_dict() or {}
            part = Participation.from_firestore(new_autor, part_data)
        else:
            part = Participation(autor=new_autor)
        bucket = getattr(part, bucket_name)
        already_in_bucket = args.doc_id in bucket
        if not already_in_bucket:
            bucket.append(args.doc_id)
        print(
            f"\nParticipation target: "
            f"participacion/{args.to_season}/authors/{new_autor} "
            f"(bucket={bucket_name})"
        )
        print(
            f"  before: total={part.total - (0 if already_in_bucket else 1)}  "
            f"{bucket_name}={len(bucket) - (0 if already_in_bucket else 1)}"
        )
        print(
            f"  after : total={part.total}  {bucket_name}={len(bucket)}  "
            f"(no-op: {already_in_bucket})"
        )

    if not args.apply:
        print("\n(dry-run) skipping writes.")
        return

    target_ref = (
        client.collection(f"comunicados/{args.to_season}/messages")
        .document(args.doc_id)
    )
    target_ref.set(target_data)
    print(f"\nWrote comunicados/{args.to_season}/messages/{args.doc_id}.")

    if bucket_name:
        part_ref.set(part.to_firestore())
        print(
            f"Updated participacion/{args.to_season}/authors/{new_autor} "
            f"({bucket_name} bucket)."
        )

    print("\nNote: source doc in {0} was NOT deleted. Use `wipe-season {0}` "
          "or delete it manually if needed.".format(args.from_season))


def _cmd_wipe_season(args) -> None:
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] Wipe scraper data under season {args.season}\n")

    client = get_client()
    plan: list[tuple[str, list]] = []
    for template in _SCRAPER_SUBCOLLECTIONS:
        path = template.format(s=args.season)
        snaps = list(client.collection(path).stream())
        plan.append((path, snaps))
        print(f"  {path:40s}  {len(snaps)} doc(s)")

    total = sum(len(s) for _, s in plan)
    print(f"\nTotal: {total} doc(s) to delete.")

    if not args.apply:
        print("\n(dry-run) skipping deletes.")
        return

    deleted = 0
    for path, snaps in plan:
        for snap in snaps:
            snap.reference.delete()
        deleted += len(snaps)
        print(f"Deleted {len(snaps)} from {path}.")
    print(f"\nDone. Deleted {deleted} doc(s) total.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-messages", help="List comunicados for a season.")
    p_list.add_argument("season", help="Season key, e.g. 25-26")
    p_list.add_argument("--author", help="Filter by autor exact match.")
    p_list.add_argument("--limit", type=int, help="Max rows to print.")
    p_list.set_defaults(func=_cmd_list_messages)

    p_move = sub.add_parser("move-message", help="Copy a message to another season.")
    p_move.add_argument("from_season", metavar="FROM", help="Source season, e.g. 26-27")
    p_move.add_argument("to_season", metavar="TO", help="Destination season, e.g. 25-26")
    p_move.add_argument("--doc-id", required=True, help="id_hash of the message.")
    p_move.add_argument(
        "--rename-author",
        help="Rewrite autor on the destination doc (id_hash is unaffected).",
    )
    p_move.add_argument("--apply", action="store_true", help="Actually write.")
    p_move.set_defaults(func=_cmd_move_message)

    p_wipe = sub.add_parser(
        "wipe-season", help="Delete all scraper data for a season."
    )
    p_wipe.add_argument("season", help="Season key, e.g. 26-27")
    p_wipe.add_argument("--apply", action="store_true", help="Actually delete.")
    p_wipe.set_defaults(func=_cmd_wipe_season)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
