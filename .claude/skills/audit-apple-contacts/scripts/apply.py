"""Apply approved decisions to Apple Contacts.

Refuses to touch anything the owner did not approve, and defaults to a dry
run: `--commit` is the only way to write. Every card is addressed by its
AppleScript id and re-checked by name before it is touched, because an id that
has gone stale silently points at a different person.
"""

import argparse
import datetime
import json
import os
import subprocess

APPLESCRIPT_TIMEOUT = 900


def quote(text):
    """Escape a value for embedding in an AppleScript string literal."""
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def build_person_script(record):
    """AppleScript that creates one card with everything the record holds.

    Kept pure so the escaping can be tested without a Mac: a stray quote in a
    note is the kind of thing that turns a create into a syntax error, or
    worse, into a different command.
    """
    lines = ['tell application "Contacts"', "  set p to make new person with properties "
             + "{{first name:\"{}\", last name:\"{}\"}}".format(
                 quote(record.get("given") or record.get("full_name", "")),
                 quote(record.get("surname", "")))]
    if record.get("organisation"):
        lines.append(f'  set organization of p to "{quote(record["organisation"])}"')
    for phone in record.get("phones", []):
        lines.append('  make new phone at end of phones of p with properties '
                     f'{{label:"móvil", value:"{quote(phone)}"}}')
    for mail in record.get("emails", []):
        lines.append('  make new email at end of emails of p with properties '
                     f'{{label:"casa", value:"{quote(mail)}"}}')
    for note in record.get("extras", {}).get("NOTE", []):
        lines.append(f'  set note of p to "{quote(note)}"')
    lines.append("  save")
    lines.append("  return id of p")
    lines.append("end tell")
    return "\n".join(lines)


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


def read_fields(apple_id):
    """Current first name, last name and organisation, for the journal."""
    quoted = quote(apple_id)
    raw = osascript(
        'tell application "Contacts"\n'
        f'  set m to (every person whose id is "{quoted}")\n'
        '  if (count of m) is 0 then return ""\n'
        "  set p to item 1 of m\n"
        '  return (first name of p as text) & "|" & (last name of p as text) '
        '& "|" & (organization of p as text)\n'
        "end tell"
    )
    # AppleScript renders an empty field as the literal «missing value», which
    # would read as a difference against the empty string it was just given.
    parts = [("" if p.strip() == "missing value" else p)
             for p in (raw.split("|") + ["", "", ""])[:3]]
    return {"first_name": parts[0], "last_name": parts[1], "organisation": parts[2]}


def write_fields(apple_id, changes):
    quoted = quote(apple_id)
    lines = ['tell application "Contacts"',
             f'  set p to first person whose id is "{quoted}"']
    if "first_name" in changes:
        lines.append(f'  set first name of p to "{quote(changes["first_name"])}"')
    if "last_name" in changes:
        lines.append(f'  set last name of p to "{quote(changes["last_name"])}"')
    if "organisation" in changes:
        lines.append(f'  set organization of p to "{quote(changes["organisation"])}"')
    lines += ["  save", "end tell"]
    osascript("\n".join(lines))


def delete_person(apple_id):
    quoted = apple_id.replace('"', '\\"')
    osascript(
        'tell application "Contacts"\n'
        f'  delete (first person whose id is "{quoted}")\n'
        "  save\n"
        "end tell"
    )


def journal_append(directory, entry):
    """Append-only record of what was written, so undo is surgical.

    Restoring a whole archive to reverse one batch is the wrong shape: it
    reverts everything else with it. Knowing the id of each card that was
    created reverses exactly the batch and nothing more.
    """
    path = os.path.join(directory, "applied.json")
    entries = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    entry["at"] = datetime.datetime.now().isoformat(timespec="seconds")
    entries.append(entry)
    json.dump(entries, open(path, "w"), ensure_ascii=False, indent=1)


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
        if action.get("changes"):
            previous = read_fields(apple_id)
            # Writing a field that already holds the value is a needless write
            # on a synced record, so only the real differences are sent.
            wanted = {k: v for k, v in action["changes"].items() if previous.get(k, "") != v}
            if not wanted:
                print(f"  already right  «{live}»")
                continue
            if args.commit:
                write_fields(apple_id, wanted)
                confirmed = read_fields(apple_id)
                if confirmed != {**previous, **wanted}:
                    print(f"  MISMATCH  «{live}» — wrote {wanted}, card now {confirmed}")
                journal_append(args.dir, {"action": action["id"], "kind": action["kind"],
                                          "operation": "edit", "apple_id": apple_id,
                                          "before": previous, "after": confirmed})
                print(f"  EDITED   «{live}» → «{wanted.get('first_name', live)}»"
                      + (f" · org «{wanted['organisation']}»" if wanted.get("organisation") else ""))
            else:
                print(f"  would edit  «{live}»")
                for field, value in wanted.items():
                    if previous.get(field, "") != value:
                        print(f"      {field}: «{previous.get(field, '')}» → «{value}»")
        elif args.commit:
            delete_person(apple_id)
            journal_append(args.dir, {"action": action["id"], "kind": action["kind"],
                                      "operation": "delete", "apple_id": apple_id,
                                      "record": record})
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
