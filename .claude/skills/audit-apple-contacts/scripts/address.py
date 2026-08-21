"""Move an address out of a note and into the address field.

In a real address book most street addresses live in the note, where they are
text: no map, no search by place. This promotes one to the field it belongs in
and takes exactly the lines it came from out of the note, leaving whatever else
was written there.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import apply  # noqa: E402


def note_without(note, drop):
    """The note with the given 1-based lines removed, blanks collapsed.

    Removing a line is not the same as blanking it: a note left as «\n\n» reads
    as content in some clients and as nothing in others.
    """
    # The numbering is the one the reader sees, so blank lines do not count.
    # Numbering the raw lines instead silently removed the blanks and left the
    # address exactly where it was.
    drop = set(drop)
    keep, seen = [], 0
    for line in (note or "").split("\n"):
        if line.strip():
            seen += 1
            if seen in drop:
                continue
        keep.append(line)
    while keep and not keep[0].strip():
        keep.pop(0)
    while keep and not keep[-1].strip():
        keep.pop()
    return "\n".join(keep)


def read_note(apple_id):
    return apply.osascript(
        'tell application "Contacts"\n'
        f'  set m to (every person whose id is "{apply.quote(apple_id)}")\n'
        '  if (count of m) is 0 then return ""\n'
        "  return note of item 1 of m\n"
        "end tell"
    )


def find_person(name):
    raw = apply.osascript(
        'tell application "Contacts"\n'
        f'  set m to (every person whose name is "{apply.quote(name)}")\n'
        '  if (count of m) is 0 then return ""\n'
        '  if (count of m) > 1 then return "AMBIGUOUS"\n'
        "  return id of item 1 of m\n"
        "end tell"
    ).strip()
    return raw


def write(apple_id, street, city, postcode, label, note):
    lines = ['tell application "Contacts"',
             f'  set p to first person whose id is "{apply.quote(apple_id)}"',
             '  make new address at end of addresses of p with properties '
             f'{{label:"{apply.quote(label)}", street:"{apply.quote(street)}", '
             f'city:"{apply.quote(city)}", zip:"{apply.quote(postcode)}", '
             'country:"España"}']
    lines.append(f'  set note of p to "{apply.quote(note)}"')
    lines += ["  save", "end tell"]
    apply.osascript("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="where the journal lives")
    parser.add_argument("--name", required=True, help="the card, by its exact name")
    parser.add_argument("--street", default="", help="omit with --note-only")
    parser.add_argument("--note-only", action="store_true",
                        help="drop the lines without creating an address")
    parser.add_argument("--city", default="")
    parser.add_argument("--postcode", default="")
    parser.add_argument("--label", default="casa")
    parser.add_argument("--drop", default="", help="note lines to remove, e.g. 1,2")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    apply.ensure_app_running()
    apple_id = find_person(args.name)
    if not apple_id:
        print(f"  NOT FOUND  «{args.name}»")
        return 1
    if apple_id == "AMBIGUOUS":
        print(f"  AMBIGUOUS  «{args.name}» matches more than one card")
        return 1

    before = read_note(apple_id)
    drop = [int(x) for x in args.drop.split(",") if x.strip()]
    after = note_without(before, drop)
    where = " · ".join(x for x in (args.street, args.city, args.postcode) if x)
    print(f"  «{args.name}»")
    if args.note_only:
        print("      sin dirección — sólo se quita de la nota")
    else:
        print(f"      dirección [{args.label}]  {where}")
    plano = lambda t: " / ".join(x.strip() for x in t.split("\n") if x.strip()) or "(vacía)"
    print(f"      nota antes  : {plano(before)}")
    print(f"      nota después: {plano(after)}")
    if not args.note_only and not args.street:
        print("  falta --street (o usa --note-only)")
        return 1
    if not args.commit:
        print("  ensayo — no se ha escrito nada")
        return 0
    if args.note_only:
        apply.osascript(
            'tell application "Contacts"\n'
            f'  set p to first person whose id is "{apply.quote(apple_id)}"\n'
            f'  set note of p to "{apply.quote(after)}"\n'
            "  save\nend tell")
    else:
        write(apple_id, args.street, args.city, args.postcode, args.label, after)
    apply.journal_append(args.dir, {"action": f"address:{args.name}", "kind": "ADDRESS",
                                    "operation": "address", "apple_id": apple_id,
                                    "before": {"note": before},
                                    "after": {"street": args.street, "city": args.city,
                                              "note": after}})
    print("  ESCRITO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
