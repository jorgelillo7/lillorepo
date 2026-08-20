"""Apply approved decisions to Apple Contacts.

Refuses to touch anything the owner did not approve, and defaults to a dry
run: `--commit` is the only way to write. Every card is addressed by its
AppleScript id and re-checked by name before it is touched, because an id that
has gone stale silently points at a different person.
"""

import argparse
import datetime
import re
import json
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vcard  # noqa: E402

APPLESCRIPT_TIMEOUT = 900


def quote(text):
    """Escape a value for embedding in an AppleScript string literal."""
    return (text or "").replace("\\", "\\\\").replace('"', '\\"')


def creation_record(record, identity, actions, decisions):
    """The record as it should be created, with the owner's answers folded in.

    Two things go wrong when the source book's name fields are copied as they
    stand. Google files the first surname in the middle-name slot, so writing
    only given and family drops it. And it takes the last word as the surname
    whatever it is, so «Andrés Reyes MM» acquires the surname «MM».
    The approved actions for this same card already say what the name should
    be, so they are applied here instead of after the fact.
    """
    prepared = dict(record)
    # The numbers are normalised in the action, not in the source record: a
    # card created from the raw export would arrive unformatted and need the
    # whole phone pass run over it again.
    for candidate in actions.values():
        if (candidate.get("identity") == identity
                and candidate["kind"] == "IMPORT"
                and candidate.get("changes", {}).get("phone_labels")):
            prepared["phone_labels"] = candidate["changes"]["phone_labels"]
            break
    # Spanish names carry two surnames, and Google files the first one in the
    # middle-name slot. It belongs with the family name, not with the given
    # one: «Álvaro | Gómez | Jiménez» is Álvaro Gómez Jiménez, not «Álvaro
    # Gómez» Jiménez. Either way the text survives; only this way is it right.
    surname = " ".join(
        part for part in (record.get("middle", ""), record.get("surname", "")) if part
    ).strip()
    # Falling back to the display name is only right when there is nothing
    # else: a card holding «Morata» in the family name and nothing in the given
    # one came out as «Morata Morata».
    prepared["given"] = record.get("given", "") or ("" if surname else record.get("full_name", ""))
    prepared["surname"] = " ".join(
        part for part in (record.get("middle", ""), record.get("surname", "")) if part
    ).strip()
    for action in actions.values():
        if action.get("identity") != identity:
            continue
        if decisions.get(action["id"], {}).get("verdict") not in ("yes", "edit"):
            continue
        override = decisions[action["id"]].get("value")
        changes = action.get("changes") or {}
        if override:
            try:
                changes = json.loads(override)
            except json.JSONDecodeError:
                pass
        if "first_name" in changes:
            prepared["given"] = changes["first_name"]
        if "last_name" in changes:
            prepared["surname"] = changes["last_name"]
        if changes.get("organisation"):
            prepared["organisation"] = changes["organisation"]
    return prepared


def build_person_script(record):
    """AppleScript that creates one card with everything the record holds.

    Kept pure so the escaping can be tested without a Mac: a stray quote in a
    note is the kind of thing that turns a create into a syntax error, or
    worse, into a different command.
    """
    lines = ['tell application "Contacts"',
             "  set p to make new person with properties "
             + '{{first name:"{}", last name:"{}"}}'.format(
                 quote(record.get("given") or record.get("full_name", "")),
                 quote(record.get("surname", "")))]
    if record.get("organisation"):
        lines.append(f'  set organization of p to "{quote(record["organisation"])}"')
    phones = record.get("phone_labels") or [["", p] for p in record.get("phones", [])]
    for label, value in phones:
        lines.append('  make new phone at end of phones of p with properties '
                     f'{{label:"{quote(label or "otro")}", value:"{quote(value)}"}}')
    emails = record.get("email_labels") or [["", m] for m in record.get("emails", [])]
    for label, value in emails:
        lines.append('  make new email at end of emails of p with properties '
                     f'{{label:"{quote(label or "otro")}", value:"{quote(value)}"}}')
    extras = record.get("extras", {})
    for note in extras.get("NOTE", []):
        lines.append(f'  set note of p to "{quote(vcard.unescape(note))}"')
    for url in extras.get("URL", []):
        lines.append('  make new url at end of urls of p with properties '
                     f'{{label:"página web", value:"{quote(vcard.unescape(url))}"}}')
    for address in extras.get("ADR", []):
        # The components arrive in the wrong slots, so reading them positionally
        # invents a city called «España». The readable line is used whole, and
        # an entry that names no street is skipped: it holds a town and nothing
        # else, which the card already says.
        readable = vcard.readable_address(address)
        if not readable:
            continue
        # «otro» says nothing. In a personal address book an address is a home
        # far more often than not, and a wrong-but-meaningful default is easier
        # to spot and correct than a meaningless one.
        lines.append('  make new address at end of addresses of p with properties '
                     f'{{label:"casa", street:"{quote(readable)}"}}')
    for birthday in extras.get("BDAY", []):
        digits = re.sub(r"\D", "", birthday)
        if len(digits) == 8:
            year, month, day = digits[:4], int(digits[4:6]), int(digits[6:])
            lines += ["  set d to current date",
                      "  set day of d to 1",
                      f"  set year of d to {year}",
                      f"  set month of d to {MONTHS[month]}",
                      f"  set day of d to {day}",
                      "  set time of d to 0",
                      "  set birth date of p to d"]
    lines.append("  save")
    lines.append("  return id of p")
    lines.append("end tell")
    return "\n".join(lines)


MONTHS = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
          6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
          11: "November", 12: "December"}


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
        '& "|" & (organization of p as text) & "|" & (middle name of p as text)\n'
        "end tell"
    )
    # AppleScript renders an empty field as the literal «missing value», which
    # would read as a difference against the empty string it was just given.
    parts = [("" if p.strip() == "missing value" else p)
             for p in (raw.split("|") + ["", "", "", ""])[:4]]
    return {"first_name": parts[0], "last_name": parts[1],
            "organisation": parts[2], "middle_name": parts[3]}


def write_fields(apple_id, changes):
    quoted = quote(apple_id)
    lines = ['tell application "Contacts"',
             f'  set p to first person whose id is "{quoted}"']
    if "first_name" in changes:
        lines.append(f'  set first name of p to "{quote(changes["first_name"])}"')
    if "last_name" in changes:
        lines.append(f'  set last name of p to "{quote(changes["last_name"])}"')
    if "middle_name" in changes:
        lines.append(f'  set middle name of p to "{quote(changes["middle_name"])}"')
    if "organisation" in changes:
        lines.append(f'  set organization of p to "{quote(changes["organisation"])}"')
    lines += ["  save", "end tell"]
    osascript("\n".join(lines))


def find_phone_index(phones, wanted):
    """Position of the number to rewrite, comparing digits only.

    The stored value can carry spaces, dashes or invisible bidi controls, so
    comparing the strings finds nothing. Returns None rather than a guess: on
    a card with several numbers, editing the wrong one is worse than skipping.
    """
    def key(value):
        digits = re.sub(r"\D", "", value or "")
        # The stored form may carry the country prefix while the audited one
        # does not, so the comparison is on the local part, as everywhere else.
        return digits[-9:] if len(digits) >= 9 else digits

    target = key(wanted)
    if not target:
        return None
    matches = [i for i, value in enumerate(phones) if key(value) == target]
    return matches[0] + 1 if len(matches) == 1 else None


def read_phones(apple_id):
    raw = osascript(
        'tell application "Contacts"\n'
        f'  set m to (every person whose id is "{quote(apple_id)}")\n'
        '  if (count of m) is 0 then return ""\n'
        '  set AppleScript\'s text item delimiters to "|"\n'
        "  return (value of every phone of item 1 of m) as text\n"
        "end tell"
    )
    return [p for p in raw.split("|")] if raw else []


def write_phone_value(apple_id, position, value):
    """Rewrite one number in place. The label is a separate property and is
    never touched, so «móvil» stays «móvil»."""
    osascript(
        'tell application "Contacts"\n'
        f'  set p to first person whose id is "{quote(apple_id)}"\n'
        f'  set value of phone {position} of p to "{quote(value)}"\n'
        "  save\n"
        "end tell"
    )


def merge_into(apple_id, changes):
    """Add what the other book had, keeping each value's own label."""
    lines = ['tell application "Contacts"',
             f'  set p to first person whose id is "{quote(apple_id)}"']
    for label, value in changes.get("add_phones", []):
        lines.append('  make new phone at end of phones of p with properties '
                     f'{{label:"{quote(label or "otro")}", value:"{quote(value)}"}}')
    for label, value in changes.get("add_emails", []):
        lines.append('  make new email at end of emails of p with properties '
                     f'{{label:"{quote(label or "otro")}", value:"{quote(value)}"}}')
    extras = changes.get("add_extras", {})
    for note in extras.get("NOTE", []):
        lines.append(f'  set note of p to "{quote(vcard.unescape(note))}"')
    for url in extras.get("URL", []):
        lines.append('  make new url at end of urls of p with properties '
                     f'{{label:"página web", value:"{quote(vcard.unescape(url))}"}}')
    lines += ["  save", "end tell"]
    osascript("\n".join(lines))
    # Anything this cannot write is reported rather than dropped: silence here
    # is how the Google profile URL nearly went missing.
    unhandled = {k: v for k, v in extras.items() if k not in ("NOTE", "URL")}
    return unhandled


def delete_person(apple_id):
    quoted = apple_id.replace('"', '\\"')
    osascript(
        'tell application "Contacts"\n'
        f'  delete (first person whose id is "{quoted}")\n'
        "  save\n"
        "end tell"
    )


def approved_actions(actions, decisions, kind):
    """The actions of one kind that carry the owner's approval.

    «edit» counts: it is the owner overriding the proposal, and it is the
    answer they took most care over. Accepting only «yes» discards it.
    """
    return [actions[i] for i, decision in decisions.items()
            if decision.get("verdict") in ("yes", "edit")
            and i in actions and actions[i]["kind"] == kind]


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
    parser.add_argument("--limit", type=int, help="apply at most this many, for a first batch")
    args = parser.parse_args()

    actions = {a["id"]: a for a in json.load(
        open(os.path.join(args.dir, "actions.json"), encoding="utf-8"))}
    decisions_path = os.path.join(args.dir, "decisions.json")
    decisions = json.load(open(decisions_path, encoding="utf-8"))
    records = json.load(open(os.path.join(args.dir, "records.json"), encoding="utf-8"))
    by_ref = {r["ref"]: r for book in records.values() for r in book}

    approved = approved_actions(actions, decisions, args.kind)
    if args.limit:
        approved = approved[: args.limit]
    if not approved:
        print(f"nothing approved for {args.kind}")
        return

    ensure_app_running()
    applied, skipped = 0, 0
    for action in approved:
        record = by_ref.get(action["ref"], {})
        if action["kind"] == "IMPORT":
            record = creation_record(record, action["identity"], actions, decisions)
            name = f"{record.get('given', '')} {record.get('surname', '')}".strip() \
                or record.get("full_name", "")
            if args.commit:
                new_id = osascript(build_person_script(record)).strip()
                journal_append(args.dir, {"action": action["id"], "kind": "IMPORT",
                                          "operation": "create", "apple_id": new_id,
                                          "record": record})
                print(f"  CREATED  «{name}»  {new_id}")
            else:
                bits = [f"{len(record.get('phones', []))} tel",
                        f"{len(record.get('emails', []))} mail"]
                bits += [k.lower() for k in record.get("extras", {})]
                if record.get("organisation"):
                    bits.append(f"org «{record['organisation']}»")
                print(f"  would create  «{name}»  ({', '.join(bits)})")
            applied += 1
            continue
        # A merge writes into the destination card, not into the record the
        # action came from, so it must not be filtered by that record having no
        # id of its own — the whole point is that it lives in the other book.
        if action.get("changes", {}).get("merge_into") is not None and action["kind"] == "MERGE":
            target = action["changes"]["merge_into"]
            live_target = read_fields(target)
            if not live_target["first_name"] and not live_target["last_name"]:
                print(f"  SKIP  {action['who']} — the card to merge into is gone")
                skipped += 1
                continue
            if args.commit:
                before = {"phones": read_phones(target), "fields": live_target}
                unhandled = merge_into(target, action["changes"])
                if unhandled:
                    print(f"  NOT WRITTEN for «{action['who']}»: {unhandled}")
                journal_append(args.dir, {"action": action["id"], "kind": "MERGE",
                                          "operation": "merge", "apple_id": target,
                                          "before": before, "added": action["changes"]})
                name = f"{live_target['first_name']} {live_target['last_name']}".strip()
                print(f"  MERGED   «{action['who']}» into «{name}»")
            else:
                print(f"  would merge  «{action['who']}» into "
                      f"«{live_target['first_name']} {live_target['last_name']}»".replace("  "," "))
                for label, value in action["changes"]["add_phones"]:
                    print(f"      + teléfono «{label}» {value}")
                for label, value in action["changes"]["add_emails"]:
                    print(f"      + correo   «{label}» {value}")
                for key, values in action["changes"]["add_extras"].items():
                    print(f"      + {key} {values}")
            applied += 1
            continue
        record = by_ref.get(action["ref"], {})
        apple_id = record.get("apple_id")
        if not apple_id:
            print(f"  SKIP  {action['who']} — not in the destination book yet; "
                  f"this applies when the card is created ({action['ref']})")
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
        if action.get("changes", {}).get("phone_from"):
            phones = read_phones(apple_id)
            position = find_phone_index(phones, action["changes"]["phone_from"])
            if position is None:
                print(f"  SKIP  {action['who']} — «{action['changes']['phone_from']}» "
                      f"is not in {phones} exactly once")
                skipped += 1
                continue
            new = action["changes"]["phone_to"]
            if args.commit:
                write_phone_value(apple_id, position, new)
                after = read_phones(apple_id)
                journal_append(args.dir, {"action": action["id"], "kind": action["kind"],
                                          "operation": "phone", "apple_id": apple_id,
                                          "before": phones, "after": after})
                ok = re.sub(r"\D", "", after[position - 1]) == re.sub(r"\D", "", new)
                print(f"  {'PHONE OK ' if ok else 'MISMATCH '} «{live}»  "
                      f"«{phones[position - 1]}» → «{after[position - 1]}»")
            else:
                print(f"  would rewrite  «{live}»  "
                      f"«{phones[position - 1]}» → «{new}»  (posición {position} de {len(phones)})")
            applied += 1
            continue
        if action.get("changes"):
            previous = read_fields(apple_id)
            override = decisions.get(action["id"], {}).get("value")
            if override:
                try:
                    action = dict(action, changes=json.loads(override))
                except json.JSONDecodeError:
                    print(f"  SKIP  {action['who']} — the correction is not valid JSON")
                    skipped += 1
                    continue
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
