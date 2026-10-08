#!/usr/bin/env python3
"""Publish the next seed questions to the public feed (ADC).

    bazel run //packages/group_polls/scripts:seed            # dry run: what would go out
    bazel run //packages/group_polls/scripts:seed -- --publish 3

Needs GROUP_POLLS_PROJECT. Each run publishes the next N questions of
seed/questions.json not published yet, in both languages (one poll per language,
each in its own feed section), open for 7 days, signed "¿Qué votáis?". Published ids
are recorded in Firestore (`seed/state`), so runs never repeat.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from packages.group_polls.scripts.seeding import load, next_batch, poll_document

PROJECT = os.environ.get("GROUP_POLLS_PROJECT", "")
QUESTIONS = Path(__file__).resolve().parent.parent / "seed" / "questions.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--publish", type=int, default=0, help="how many questions to publish"
    )
    args = parser.parse_args()
    questions = load(json.loads(QUESTIONS.read_text()))

    if not args.publish:
        for index, q in next_batch(questions, set(), 3):
            print(f"#{index}  {q['es'][0]}  /  {q['en'][0]}")
        print("Dry run. Use --publish N with GROUP_POLLS_PROJECT set.")
        return 0
    if not PROJECT:
        print("Set GROUP_POLLS_PROJECT (see OPERATIONS.md).", file=sys.stderr)
        return 2

    from google.cloud import firestore

    db = firestore.Client(project=PROJECT)
    state_ref = db.collection("seed").document("state")
    done = set((state_ref.get().to_dict() or {}).get("published", []))
    for index, q in next_batch(questions, done, args.publish):
        for language in ("es", "en"):
            code, doc = poll_document(q, language)
            doc["createdAt"] = firestore.SERVER_TIMESTAMP
            db.collection("polls").document(code).set(doc)
            print(f"#{index} {language}: {code}  {doc['question']}")
        done.add(index)
        state_ref.set({"published": sorted(done)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
