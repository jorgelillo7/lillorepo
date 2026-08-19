"""Build the action queue from two address-book exports.

Reads two vCard files, writes records.json, actions.json and REPORT.md into an
output directory. Nothing is written to the address book: this stage only
proposes. Point --out somewhere outside the repository — the output contains
real contact data.
"""

import argparse
import collections
import hashlib
import json
import os
import re

import vcard


def load_records(path, source):
    records = []
    for index, props in enumerate(vcard.parse(open(path, encoding="utf-8", errors="replace").read())):
        full = (props.get("FN") or [("", "")])[0][1].strip()
        name = (props.get("N") or [("", "")])[0][1].split(";")
        surname, given = (name + ["", ""])[:2]
        phones = [v for _, v in props.get("TEL", [])]
        records.append(
            {
                "source": source,
                "index": index,
                "ref": f"{source}#{index}",
                "full_name": full,
                "given": given.strip(),
                "surname": surname.strip(),
                "middle": (name + ["", "", ""])[2].strip(),
                "organisation": (props.get("ORG") or [("", "")])[0][1].strip(";").strip(),
                "phones": phones,
                "emails": [v.strip().lower() for _, v in props.get("EMAIL", [])],
                "phone_keys": [k for k in (vcard.phone_key(p) for p in phones) if k],
                "name_key": vcard.strip_accents(full),
                "uid": (props.get("UID") or [("", "")])[0][1].strip(),
                # X-ABUID is what AppleScript returns as «id of person», so it
                # is the only key an apply step can address a card by. The
                # vCard UID is a different namespace and finds nothing.
                "apple_id": (props.get("X-ABUID") or [("", "")])[0][1].strip(),
                # A card with neither UID nor the «card» category was created
                # locally and never reached iCloud, so it exists on this Mac
                # and on no other device. Heuristic, but it matched every case.
                # Only meaningful for cards that came out of Apple Contacts,
                # which is what X-ABUID identifies. Another exporter omits UID
                # for reasons of its own and would be flagged wrongly.
                "local_only": bool(props.get("X-ABUID")) and not (
                    props.get("UID")
                    and any(v.strip() == "card" for _, v in props.get("CATEGORIES", []))
                ),
                "extras": {
                    key: [v.strip(" ;") for _, v in props[key] if v.strip(" ;")]
                    for key in ("NOTE", "ADR", "BDAY", "URL", "TITLE")
                    if key in props and any(v.strip(" ;") for _, v in props[key])
                },
            }
        )
    return records


def action_id(kind, ref, before):
    """Stable across regeneration: a counter would renumber and invalidate
    decisions already taken."""
    seed = f"{kind}|{ref}|{before}".encode()
    return f"{kind}-{hashlib.sha1(seed).hexdigest()[:8]}"


def build(primary, secondary, config):
    # Records may arrive from a caller that predates a field. Filling the
    # defaults once here keeps every rule below free of .get() noise.
    for record in list(primary) + list(secondary):
        for key, empty in (("middle", ""), ("apple_id", ""),
                           ("local_only", False), ("extras", {})):
            record.setdefault(key, empty)

    prefix = config.get("country_prefix", "+34")
    length = config.get("local_length", 9)
    actions = []

    def add(kind, record, before, after, note=""):
        actions.append(
            {
                "id": action_id(kind, record.get("ref", "-"), before),
                "kind": kind,
                "source": record.get("source", "-"),
                "ref": record.get("ref", "-"),
                "who": record.get("full_name") or record.get("organisation") or "(no name)",
                "before": before,
                "after": after,
                "note": note,
            }
        )

    for record in primary + secondary:
        if record["phones"] or record["emails"]:
            continue
        # A card with no phone and no email can still be the only place an
        # address or a birthday is written down. Deleting it silently loses
        # that, so whatever it holds goes in the note the owner reads.
        keeps = dict(record["extras"])
        if record["organisation"]:
            keeps["ORG"] = [record["organisation"]]
        note = "no phone and no email"
        if record.get("local_only"):
            note += " · local to this Mac, never synced to iCloud"
        if keeps:
            note += " — but it holds " + ", ".join(
                f"{key} {value}" for key, value in keeps.items())
        add("EMPTY", record, f"org={record['organisation'] or '—'}", "delete the card", note)

    for record in primary:
        for phone in record["phones"]:
            fixed = vcard.normalize_phone(phone, prefix, length)
            if fixed != phone:
                note = ""
                if any(ord(c) < 32 or 0x200B <= ord(c) <= 0x206F for c in phone):
                    note = "carries invisible bidi controls, which is why before/after look alike"
                add("PHONE", record, phone, fixed, note)

    for record in primary + secondary:
        for pattern, canonical in config.get("organisations", {}).items():
            if re.search(pattern, vcard.strip_accents(record["full_name"]), re.I):
                cleaned = re.sub(pattern, "", record["full_name"], flags=re.I)
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,[]")
                clash = record["organisation"] and vcard.strip_accents(
                    record["organisation"]
                ) != vcard.strip_accents(canonical)
                kind = "CLASH" if clash else "ORG"
                add(kind, record,
                    f"name «{record['full_name']}» · org={record['organisation'] or '—'}",
                    f"name «{cleaned}» · org={canonical}",
                    "the name says one company and the org field another" if clash else "")
                break

    for record in primary + secondary:
        for rule in config.get("rewrites", []):
            match = re.match(rule["match"], vcard.strip_accents(record["full_name"]), re.I)
            if not match:
                continue
            groups = [vcard.pretty(g, config.get("spelling", {})) for g in match.groups()]
            name = rule["name"]
            for position, group in enumerate(groups, 1):
                name = name.replace(f"\\{position}", group)
            org = rule.get("organisation", record["organisation"])
            add("REWRITE", record,
                f"name «{record['full_name']}» · org={record['organisation'] or '—'}",
                f"name «{name}» · org={org}", rule.get("note", ""))
            break

    for record in primary + secondary:
        # A tag typed into the structured name pushes the real surname into
        # the middle-name slot. The card then sorts under «#» instead of its
        # letter, which is how this usually gets noticed.
        tagged = re.search(r"[<>()\[\]]", record["surname"])
        if tagged or (record["middle"] and not record["surname"]):
            clean = re.sub(r"[<(\[].*?[>)\]]", "", record["full_name"])
            tokens = re.sub(r"\s+", " ", clean).strip().split()
            proposal = (f"given=«{tokens[0]}» surname=«{' '.join(tokens[1:])}»"
                        if len(tokens) > 1 else f"given=«{clean.strip()}» surname=«»")
            add("NFIELD", record,
                f"N={record['surname']};{record['given']};{record['middle']}",
                proposal,
                "the tag in the name field belongs in the company field or the note")

    for record in primary + secondary:
        flipped = vcard.flip_inverted(record["full_name"])
        if flipped != record["full_name"]:
            add("FLIP", record, record["full_name"], flipped, "inherited from a Google export")

    for record in primary + secondary:
        if vcard.relationship_at_end(record["full_name"], config.get("kinship", "")):
            tokens = record["full_name"].split()
            add("KIN", record, record["full_name"],
                f"{tokens[-1].capitalize()} {' '.join(tokens[:-1])}",
                "moves to the majority form «Kinship Name»")

    for record in primary:
        if record["surname"] or not record["full_name"] or record["organisation"]:
            continue
        tokens = record["full_name"].split()
        if len(tokens) == 1:
            add("ASK", record, f"only «{record['full_name']}»", "surname?", "tell me if you know it")
        elif len(tokens) == 2:
            add("SPLIT", record, record["full_name"],
                f"given=«{tokens[0]}» surname=«{tokens[1]}»", "safe split")
        else:
            add("SPLIT3", record, record["full_name"],
                f"A) «{' '.join(tokens[:-1])}»+«{tokens[-1]}»   "
                f"B) «{' '.join(tokens[:-2])}»+«{' '.join(tokens[-2:])}»",
                "two surnames is the norm here, so usually B")

    matched = vcard.match(secondary, primary)
    for record, hits in matched:
        if len(hits) > 1:
            add("CLASH", record, f"matches {[h[0]['full_name'] for h in hits]}",
                "which one is the same person?",
                "a shared household landline matches people who are not the same")
        elif not hits and (record["phones"] or record["emails"]):
            carried = {
                "tel": [vcard.normalize_phone(p, prefix, length) for p in record["phones"]],
                "mail": record["emails"],
                "org": [record["organisation"]] if record["organisation"] else [],
            }
            carried.update({k.lower(): v for k, v in record["extras"].items()})
            # Notes and addresses are frequently the only place a street
            # address is written down, so the import carries every field and
            # says which, rather than quietly creating a name and a number.
            summary = " · ".join(f"{k}={v}" for k, v in carried.items() if v)
            add("IMPORT", record,
                f"tel={record['phones'] or '—'} mail={record['emails'] or '—'} "
                f"org={record['organisation'] or '—'}"
                + (f" · also {list(record['extras'])}" if record["extras"] else ""),
                f"create · {summary}")
    return actions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", required=True, help="NAME=FILE — the destination book")
    parser.add_argument("--secondary", required=True, help="NAME=FILE — the book being merged in")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True, help="output directory, outside the repository")
    args = parser.parse_args()

    config = json.load(open(args.config, encoding="utf-8"))
    pname, ppath = args.primary.split("=", 1)
    sname, spath = args.secondary.split("=", 1)
    primary, secondary = load_records(ppath, pname), load_records(spath, sname)

    numbers = [p for r in primary + secondary for p in r["phones"]]
    safe, offenders = vcard.blanket_prefix_safe(
        numbers, config.get("local_length", 9), config.get("local_first_digits", "6789"))

    os.makedirs(args.out, exist_ok=True)
    actions = build(primary, secondary, config)
    json.dump({pname: primary, sname: secondary}, open(os.path.join(args.out, "records.json"), "w"),
              ensure_ascii=False, indent=1)
    json.dump(actions, open(os.path.join(args.out, "actions.json"), "w"),
              ensure_ascii=False, indent=1)

    counts = collections.Counter(a["kind"] for a in actions)
    print(f"{pname}={len(primary)}  {sname}={len(secondary)}  actions={len(actions)}")
    for kind, total in counts.most_common():
        print(f"  {kind:8s} {total}")
    if not safe:
        print(f"\n  WARNING: blanket country prefix is unsafe for {offenders}")
    else:
        print(f"\n  country prefix verified safe for all {len(numbers)} numbers in these files")


if __name__ == "__main__":
    main()
