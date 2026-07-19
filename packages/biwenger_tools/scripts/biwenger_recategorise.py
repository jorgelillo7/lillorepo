#!/usr/bin/env python3
"""Re-categorise messages and rebuild participacion for a season.

For every message in ``comunicados/{season}/messages`` whose stored
``categoria`` doesn't match ``categorize_title(titulo)``, this script
updates the doc. After fixing categorías, it rebuilds
``participacion/{season}/authors`` from scratch so the per-author totals
reflect the corrected categorización.

Use ``--autor-alias OLD=NEW`` (repeatable) to also rewrite the ``autor``
field on every message where ``autor == OLD``. The synthetic case is
when an account was deleted mid-season and the scraper fell back to
``Autor Desconocido``; this lets you attribute those messages to the
real team name.

Default is dry-run; pass ``--apply`` to actually write Firestore.

Usage::

    # Inspect what would change for the current season
    python3 scripts/biwenger_recategorise.py 25-26

    # Apply, also reassigning a stale author fallback
    python3 scripts/biwenger_recategorise.py 25-26 --apply \\
        --autor-alias 'Autor Desconocido=#NOALOSCLAUSULAZOS'
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.domain.models import LeagueMessage  # noqa: E402
from core.sdk.firestore import get_client  # noqa: E402
from packages.biwenger_tools.scraper_job.logic.processing import (  # noqa: E402
    categorize_title,
    process_participation,
)


def _parse_aliases(values: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            print(
                f"WARNING: --autor-alias '{raw}' is malformed "
                "(need OLD=NEW); skipped.",
                file=sys.stderr,
            )
            continue
        old, _, new = raw.partition("=")
        aliases[old.strip()] = new.strip()
    return aliases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="Season key, e.g. 25-26")
    parser.add_argument(
        "--apply", action="store_true", help="Actually write to Firestore."
    )
    parser.add_argument(
        "--autor-alias",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Reassign autor on every message; repeatable.",
    )
    args = parser.parse_args()
    aliases = _parse_aliases(args.autor_alias)
    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"[{mode}] Re-categorise messages for {args.season}")
    if aliases:
        print(f"Aliases: {aliases}")

    client = get_client()
    messages_coll = client.collection(f"comunicados/{args.season}/messages")

    # --- Step 1: Walk messages, decide what to change ---
    pending_updates = []
    for snap in messages_coll.stream():
        data = snap.to_dict() or {}
        updates: dict = {}
        expected = categorize_title(data.get("titulo", ""))
        if expected != (data.get("categoria") or ""):
            updates["categoria"] = expected
        new_autor = aliases.get(data.get("autor"))
        if new_autor:
            updates["autor"] = new_autor
        if updates:
            pending_updates.append((snap, data, updates))

    print(f"\n{len(pending_updates)} message docs need updates.")
    for snap, data, updates in pending_updates:
        print(
            f"  {str(data.get('fecha', ''))[:19]:20s}  "
            f"{data.get('autor', ''):30s}  "
            f"{data.get('titulo', '')!r:30s}  {updates}"
        )

    if args.apply:
        for snap, _, updates in pending_updates:
            snap.reference.update(updates)
        print(f"\nUpdated {len(pending_updates)} message docs.")
    else:
        print("\n(dry-run) skipping message updates.")

    # --- Step 2: Rebuild participacion ---
    # Re-read so the post-update state is used when --apply was passed.
    all_messages = [
        LeagueMessage.from_firestore(snap.id, snap.to_dict() or {})
        for snap in messages_coll.stream()
    ]
    # Roster = every team_name in palmares.standings_table when available
    # (authoritative, includes members who never posted), plus any author
    # we still see in messages but isn't in the palmares (e.g. when the
    # palmares doc hasn't been written yet for an in-flight season).
    roster: set[str] = set()
    palmares_doc = (
        client.collection("palmares").document(args.season).get().to_dict() or {}
    )
    for row in palmares_doc.get("standings_table") or []:
        team_name = (row.get("team_name") or "").strip()
        if team_name and team_name != "—":
            roster.add(team_name)
    roster.update(
        m.autor for m in all_messages if m.autor and m.autor != "Autor Desconocido"
    )
    synthetic_user_map = {i: name for i, name in enumerate(sorted(roster))}
    participaciones = list(process_participation(all_messages, synthetic_user_map))

    print(f"\nNew participacion totals ({len(participaciones)} authors):")
    for p in sorted(participaciones, key=lambda p: -p.total):
        print(
            f"  {p.autor:30s}  total={p.total:3d}  "
            f"comunicados={len(p.comunicados):3d}  datos={len(p.datos):3d}  "
            f"cronicas={len(p.cronicas):3d}  cesiones={len(p.cesiones):3d}"
        )

    if args.apply:
        existing = list(
            client.collection(f"participacion/{args.season}/authors").stream()
        )
        for snap in existing:
            snap.reference.delete()
        for p in participaciones:
            client.collection(f"participacion/{args.season}/authors").document(
                p.autor
            ).set(p.to_firestore())
        print(
            f"\nWiped {len(existing)} existing participacion docs; "
            f"wrote {len(participaciones)} fresh ones."
        )
    else:
        print("\n(dry-run) skipping participacion rebuild.")

    print("\nDone.")


if __name__ == "__main__":
    main()
