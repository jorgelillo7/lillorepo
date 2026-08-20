"""Approve the proposed actions, one contact at a time.

Two modes share one decisions file, so a session can move between them:

  --interactive   a keyboard loop for working through a block alone
  --list/--decide a headless mode, for an agent relaying each action in a
                  conversation and recording the answer

Every decision is written to disk as it is taken. A bulk approval that only
saved at the end would lose the whole block if the session died mid-way.
"""

import argparse
import collections
import json
import os

ORDER = ["EMPTY", "KNOWN", "REWRITE", "KIN", "FLIP", "ORG", "PHONE", "SPLIT", "SPLIT3", "ASK",
         "NFIELD", "MERGE", "CLASH", "IMPORT"]
TITLES = {
    "EMPTY": "Cards with no phone and no email",
    "KNOWN": "What the owner told me, as a proposal to confirm",
    "REWRITE": "Names matching a rewrite rule from the config",
    "KIN": "Kinship word trailing the name",
    "FLIP": "Name stored as «Surname, Given»",
    "ORG": "Company embedded in the name",
    "PHONE": "Phone numbers to normalise",
    "SPLIT": "Split given name and surname (two words)",
    "SPLIT3": "Split given name and surname (three or more)",
    "ASK": "Surname missing — needs the owner",
    "NFIELD": "Structured name holds a tag, so the card sorts under #",
    "MERGE": "Already in the destination book — add, do not duplicate",
    "CLASH": "Needs judgement, no automatic answer",
    "IMPORT": "Create in the destination book",
}
VALID = {"yes", "no", "edit", "unknown"}


class Store:
    def __init__(self, directory):
        self.actions = json.load(open(os.path.join(directory, "actions.json"), encoding="utf-8"))
        self.path = os.path.join(directory, "decisions.json")
        self.decisions = json.load(open(self.path, encoding="utf-8")) if os.path.exists(self.path) else {}
        self.by_id = {a["id"]: a for a in self.actions}

    def save(self):
        json.dump(self.decisions, open(self.path, "w"), ensure_ascii=False, indent=1)

    def pending(self, kind=None):
        return [a for a in self.actions
                if a["id"] not in self.decisions and (kind is None or a["kind"] == kind)]

    def decide(self, action_id, verdict, value=None):
        if action_id not in self.by_id:
            raise KeyError(f"unknown action {action_id}")
        if verdict not in VALID:
            raise ValueError(f"verdict must be one of {sorted(VALID)}")
        entry = {"verdict": verdict}
        if value:
            entry["value"] = value
        self.decisions[action_id] = entry
        self.save()
        return self.by_id[action_id]


def show(action, index=None, total=None):
    head = f"[{index}/{total}] " if index else ""
    print(f"\n{head}{action['id']}  {action['who']}   ({action['source']} {action['ref']})")
    print(f"  before: {action['before']}")
    print(f"  after : {action['after']}")
    if action["note"]:
        print(f"  note  : {action['note']}")


def status(store):
    counts = collections.Counter(a["kind"] for a in store.actions)
    done = collections.Counter(store.by_id[i]["kind"] for i in store.decisions if i in store.by_id)
    print(f"{len(store.decisions)}/{len(store.actions)} decided")
    for kind in ORDER:
        if counts[kind]:
            print(f"  {kind:8s} {done[kind]:4d}/{counts[kind]:<4d}  {TITLES.get(kind, kind)}")
    verdicts = collections.Counter(v["verdict"] for v in store.decisions.values())
    if verdicts:
        print(f"  verdicts: {dict(verdicts)}")


HELP = """
  y  yes        n  no          e  edit the value by hand
  u  unknown, decide later     A  approve the rest of this block
  q  save and quit             h  this help
"""


def interactive(store):
    print(HELP)
    for kind in ORDER:
        pending = store.pending(kind)
        if not pending:
            continue
        print(f"\n{'=' * 68}\n{TITLES.get(kind, kind)} — {len(pending)} pending\n{'=' * 68}")
        bulk = False
        for position, action in enumerate(pending, 1):
            if bulk:
                store.decide(action["id"], "yes")
                continue
            show(action, position, len(pending))
            while True:
                try:
                    key = input("  > ").strip()
                except (EOFError, KeyboardInterrupt):
                    key = "q"
                if key == "h":
                    print(HELP)
                    continue
                if key == "q":
                    return
                if key == "A":
                    bulk = True
                    store.decide(action["id"], "yes")
                    break
                if key in ("y", ""):
                    store.decide(action["id"], "yes")
                    break
                if key == "n":
                    store.decide(action["id"], "no")
                    break
                if key == "u":
                    store.decide(action["id"], "unknown")
                    break
                if key == "e":
                    value = input("    final value: ").strip()
                    if value:
                        store.decide(action["id"], "edit", value)
                        break
                    continue
                print("    unknown key — press h for help")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--list", metavar="KIND", nargs="?", const="")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--decide", action="append", default=[],
                        metavar="ID=VERDICT[:VALUE]")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    store = Store(args.dir)

    for item in args.decide:
        action_id, _, rest = item.partition("=")
        verdict, _, value = rest.partition(":")
        action = store.decide(action_id, verdict, value or None)
        print(f"  {action_id}  {verdict}{': ' + value if value else ''}   ← {action['who']}")

    if args.list is not None:
        kinds = [args.list] if args.list else ORDER
        for kind in kinds:
            pending = store.pending(kind)
            if not pending:
                continue
            print(f"\n### {kind} — {len(pending)} pending — {TITLES.get(kind, kind)}")
            for action in pending[: args.limit]:
                show(action)
            if len(pending) > args.limit:
                print(f"\n  … {len(pending) - args.limit} more")

    if args.interactive:
        interactive(store)
    if args.status or not (args.list is not None or args.decide or args.interactive):
        status(store)


if __name__ == "__main__":
    main()
