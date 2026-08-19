"""Apply approved decisions to Apple Contacts.

Refuses to touch anything the owner did not approve, and defaults to a dry
run: `--commit` is the only way to write. Every card is addressed by its
AppleScript id and re-checked by name before it is touched, because an id that
has gone stale silently points at a different person.
"""

import argparse
import json
import os
import subprocess

APPLESCRIPT_TIMEOUT = 900


def osascript(body):
    script = f"with timeout of {APPLESCRIPT_TIMEOUT} seconds\n{body}\nend timeout"
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def ensure_app_running():
    # `launch` inside the tell is not enough: Contacts answers -600 until the
    # application is actually up.
    subprocess.run(["open", "-a", "Contacts"], capture_output=True)
    osascript('tell application "Contacts" to return count of every person')


def read_name(apple_id):
    quoted = apple_id.replace('"', '\\"')
    return osascript(
        'tell application "Contacts"\n'
        f'  set matches to (every person whose id is "{quoted}")\n'
        "  if (count of matches) is 0 then return \"\"\n"
        "  return name of item 1 of matches\n"
        "end tell"
    )


def delete_person(apple_id):
    quoted = apple_id.replace('"', '\\"')
    osascript(
        'tell application "Contacts"\n'
        f'  delete (first person whose id is "{quoted}")\n'
        "  save\n"
        "end tell"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--kind", default="EMPTY", help="only this kind of action")
    parser.add_argument("--commit", action="store_true", help="actually write")
    args = parser.parse_args()

    actions = {a["id"]: a for a in json.load(
        open(os.path.join(args.dir, "actions.json"), encoding="utf-8"))}
    decisions_path = os.path.join(args.dir, "decisions.json")
    decisions = json.load(open(decisions_path, encoding="utf-8"))
    records = json.load(open(os.path.join(args.dir, "records.json"), encoding="utf-8"))
    by_ref = {r["ref"]: r for book in records.values() for r in book}

    approved = [actions[i] for i, d in decisions.items()
                if d["verdict"] == "yes" and i in actions and actions[i]["kind"] == args.kind]
    if not approved:
        print(f"nothing approved for {args.kind}")
        return

    ensure_app_running()
    applied, skipped = 0, 0
    for action in approved:
        record = by_ref.get(action["ref"], {})
        apple_id = record.get("apple_id")
        if not apple_id:
            print(f"  SKIP  {action['who']} — not an Apple card, nothing to delete here "
                  f"({action['ref']})")
            skipped += 1
            continue
        live = read_name(apple_id)
        if not live:
            print(f"  SKIP  {action['who']} — no card with that id any more")
            skipped += 1
            continue
        if live.strip() != (record.get("full_name") or "").strip():
            print(f"  SKIP  {action['who']} — the card now reads «{live}», refusing")
            skipped += 1
            continue
        if args.commit:
            delete_person(apple_id)
            print(f"  DELETED  «{live}»")
        else:
            print(f"  would delete  «{live}»   ({apple_id})")
        applied += 1
    verb = "applied" if args.commit else "planned"
    print(f"\n{verb}: {applied}   skipped: {skipped}")
    if not args.commit:
        print("dry run — nothing was written. Re-run with --commit.")


if __name__ == "__main__":
    main()
