#!/usr/bin/env python3
"""Moderate "¿Qué votáis?" public polls (ADC, project from GROUP_POLLS_PROJECT).

    bazel run //packages/group_polls/scripts:moderate                  # review queue
    bazel run //packages/group_polls/scripts:moderate -- show CODE     # one poll
    bazel run //packages/group_polls/scripts:moderate -- restore CODE  # unhide
    bazel run //packages/group_polls/scripts:moderate -- remove CODE   # delete
    bazel run //packages/group_polls/scripts:moderate -- stats         # last 7 days

`restore` makes a wrongly hidden poll visible and clears its reports; `remove`
deletes an abusive one with its votes and reports. Runs with your own credentials,
so security rules do not apply: every write is behind a confirmation. Polls hide
themselves after 3 reports; this is the manual review the app's terms promise.
"""

import argparse
import datetime as dt
import os
import sys

from google.cloud import firestore

from packages.group_polls.scripts.moderation import review_queue, summary

PROJECT = os.environ.get("GROUP_POLLS_PROJECT", "")


def _confirm(text: str) -> bool:
    try:
        return input(f"{text} [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def _delete_collection(ref) -> int:
    deleted = 0
    for doc in ref.stream():
        doc.reference.delete()
        deleted += 1
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="queue",
        choices=["queue", "show", "restore", "remove", "stats"],
    )
    parser.add_argument("code", nargs="?")
    args = parser.parse_args()
    if not PROJECT:
        print(
            "Set GROUP_POLLS_PROJECT to the GCP project id (see OPERATIONS.md).",
            file=sys.stderr,
        )
        return 2

    db = firestore.Client(project=PROJECT)
    polls = db.collection("polls")
    now = dt.datetime.now(dt.UTC)

    if args.action == "queue":
        reported = {
            d.id: d.to_dict()
            for d in polls.where(
                filter=firestore.FieldFilter("reports", ">", 0)
            ).stream()
        }
        queue = review_queue(reported)
        if not queue:
            print("Nothing to review. ✨")
        for code in queue:
            print(summary(code, reported[code], now))
        return 0

    if args.action == "stats":
        since = now - dt.timedelta(days=7)
        recent = [
            d.to_dict()
            for d in polls.where(
                filter=firestore.FieldFilter("createdAt", ">", since)
            ).stream()
        ]
        public = sum(1 for p in recent if p.get("visibility") == "public")
        votes = sum(
            int(p.get("redVotes", 0)) + int(p.get("blueVotes", 0)) for p in recent
        )
        private = len(recent) - public
        print(
            f"Last 7 days: {len(recent)} polls ({public} public, {private} private),"
            f" {votes} votes on them."
        )
        return 0

    if not args.code:
        parser.error(f"{args.action} needs a poll code")
    ref = polls.document(args.code)
    snapshot = ref.get()
    if not snapshot.exists:
        print(f"No poll {args.code}.", file=sys.stderr)
        return 1
    print(summary(args.code, snapshot.to_dict(), now))

    if args.action == "restore" and _confirm(
        "Make it visible again and clear its reports?"
    ):
        cleared = _delete_collection(ref.collection("reports"))
        ref.update({"hidden": False, "reports": 0})
        print(f"Restored ({cleared} reports cleared).")
    elif args.action == "remove" and _confirm(
        "Delete this poll, its votes and its reports for good?"
    ):
        votes = _delete_collection(ref.collection("votes"))
        reports = _delete_collection(ref.collection("reports"))
        ref.delete()
        print(f"Removed ({votes} votes, {reports} reports).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
