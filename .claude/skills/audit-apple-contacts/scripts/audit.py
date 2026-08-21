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
        phone_labels = vcard.labelled(props, "TEL")
        email_labels = vcard.labelled(props, "EMAIL")
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
                "phone_labels": phone_labels,
                "email_labels": email_labels,
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


def identity(record):
    """A key that survives re-exporting the book.

    The positional ref does not: deleting one card shifts every index after
    it, so an id built on the ref quietly points at a different person the
    next time the audit runs. Apple's own id is stable; a book that has none
    is keyed on what it does have.
    """
    if record.get("apple_id"):
        return record["apple_id"]
    seed = "|".join([record.get("source", ""), record.get("full_name", "")]
                    + sorted(record.get("phone_keys", []))
                    + sorted(record.get("emails", [])))
    return f"{record.get('source', '')}:{hashlib.sha1(seed.encode()).hexdigest()[:12]}"


def action_id(kind, key, before):
    """Stable across regeneration: a counter would renumber and invalidate
    decisions already taken."""
    seed = f"{kind}|{key}|{before}".encode()
    return f"{kind}-{hashlib.sha1(seed).hexdigest()[:8]}"


def build(primary, secondary, config):
    # Records may arrive from a caller that predates a field. Filling the
    # defaults once here keeps every rule below free of .get() noise.
    for record in list(primary) + list(secondary):
        for key, empty in (("middle", ""), ("apple_id", ""), ("local_only", False),
                           ("extras", {}), ("phone_labels", None), ("email_labels", None)):
            record.setdefault(key, empty)
        # Derive the labelled forms when a caller supplied only bare values.
        if record["phone_labels"] is None:
            record["phone_labels"] = [["", value] for value in record["phones"]]
        if record["email_labels"] is None:
            record["email_labels"] = [["", value] for value in record["emails"]]

    prefix = config.get("country_prefix", "+34")
    length = config.get("local_length", 9)
    actions = []

    def add(kind, record, before, after, note="", changes=None):
        actions.append(
            {
                "id": action_id(kind, identity(record), before),
                "identity": identity(record),
                "kind": kind,
                "source": record.get("source", "-"),
                "ref": record.get("ref", "-"),
                "who": record.get("full_name") or record.get("organisation") or "(no name)",
                "before": before,
                "after": after,
                "note": note,
                # What to write, field by field. Parsing it back out of the
                # human-readable «after» would break the moment that string is
                # reworded.
                "changes": changes or {},
            }
        )

    # Facts the owner supplied. They enter the queue as proposals like anything
    # else — being told something is not the same as it being approved — but
    # they outrank every rule, because a rule is guessing and the owner is not.
    for record in primary + secondary:
        for fact in config.get("known", []):
            if vcard.strip_accents(fact["name"]) != vcard.strip_accents(record["full_name"]):
                continue
            changes = {k: v for k, v in (
                ("first_name", fact.get("given")),
                ("last_name", fact.get("surname")),
                ("middle_name", ""),
                ("organisation", fact.get("organisation")),
            ) if v is not None}
            after = " · ".join(f"{k}=«{v}»" for k, v in changes.items() if k != "middle_name")
            add("KNOWN", record,
                f"name «{record['full_name']}» · org={record['organisation'] or '—'}",
                after, fact.get("note", "you told me this"), changes=changes)
            break

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
                add("PHONE", record, phone, fixed, note,
                    changes={"phone_from": phone, "phone_to": fixed})

    for record in primary + secondary:
        for pattern, canonical in config.get("organisations", {}).items():
            if re.search(pattern, vcard.strip_accents(record["full_name"]), re.I):
                cleaned = re.sub(pattern, "", record["full_name"], flags=re.I)
                # Removing «Accenture» from «Javi Griñan <Accenture>» leaves the
                # brackets behind; an empty pair reads as a typo, not a name.
                cleaned = re.sub(r"[<(\[]\s*[>)\]]", "", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,[]()<>")
                clash = record["organisation"] and vcard.strip_accents(
                    record["organisation"]
                ) != vcard.strip_accents(canonical)
                kind = "CLASH" if clash else "ORG"
                # Everything left of the tag goes in the given name and the
                # surname is cleared. Splitting on the last word is wrong more
                # often than not here — «ingrid tecnico» would acquire the
                # surname «tecnico» — so a real surname comes from the owner.
                add(kind, record,
                    f"name «{record['full_name']}» · org={record['organisation'] or '—'}",
                    f"name «{cleaned}» · org={canonical}",
                    "the name says one company and the org field another" if clash else "",
                    changes=None if clash else {
                        "first_name": cleaned, "last_name": "", "middle_name": "",
                        "organisation": canonical})
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
                f"name «{name}» · org={org}", rule.get("note", ""),
                changes={"first_name": name, "last_name": "", "organisation": org})
            break

    for record in primary + secondary:
        # A name that opens with a kinship word is not «given: Prima, family:
        # María» — it is «Prima María», one label for one person. The exporter
        # splits it on the first space like any other name, which files the
        # relationship as the given name and the person as the surname.
        first = record["full_name"].split()[:1]
        if first and re.fullmatch(config.get("kinship", ""), vcard.strip_accents(first[0]), re.I):
            if record["surname"]:
                add("KINHEAD", record,
                    f"nombre=«{record['given']}» apellido=«{record['surname']}»",
                    f"given=«{record['full_name']}» surname=«»",
                    "the relationship word belongs with the name, not in the surname field",
                    changes={"first_name": record["full_name"], "last_name": "",
                             "middle_name": ""})
                continue

    for record in primary + secondary:
        # A tag typed into the structured name pushes the real surname into
        # the middle-name slot. The card then sorts under «#» instead of its
        # letter, which is how this usually gets noticed.
        tagged = re.search(r"[<>()\[\]]", record["surname"])
        if tagged or (record["middle"] and not record["surname"]):
            # The tag is not noise: it is often the only thing identifying the
            # person («Rober (rebe)» is Rebe's Rober, and the owner may know
            # nothing else). Moving it to a note would hide it from the list,
            # which is where it is read. So the displayed name is preserved
            # exactly and only the field it lives in changes — the surname slot
            # is what makes the card sort under «#».
            display = re.sub(r"\s+", " ", record["full_name"]).strip()
            add("NFIELD", record,
                f"N={record['surname']};{record['given']};{record['middle']}",
                f"given=«{display}» surname=«» — same name, sorts by its letter",
                "the tag stays visible; only the field it sits in changes",
                changes={"first_name": display, "last_name": "", "middle_name": ""})

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

    context = config.get("context_words", {})
    kinship = config.get("kinship", "")
    for record in primary:
        if record["surname"] or not record["full_name"] or record["organisation"]:
            continue
        tokens = record["full_name"].split()
        # A name is not always a name. «Prima Gema» is one label for one
        # person, «Lorena karate» says where she is from, «Rober (rebe)» says
        # whose Rober he is. Splitting any of them puts a relationship or a
        # place in the surname field — and worse, undoes a decision already
        # taken, since these were deliberately left whole.
        plain = vcard.strip_accents(record["full_name"])
        if "(" in record["full_name"] or ")" in record["full_name"]:
            continue
        # A relationship word anywhere makes this a label, not a name. The
        # convention «Nombre Parentesco Referente» — «Javi Primo Patri», whose
        # cousin he is — puts it in the middle, where looking only at the first
        # word never finds it.
        if kinship and any(re.fullmatch(kinship, vcard.strip_accents(t), re.I)
                           for t in tokens):
            continue
        if any(re.search(pattern, plain, re.I) for pattern in context):
            continue
        if len(tokens) == 1:
            add("ASK", record, f"only «{record['full_name']}»", "surname?", "tell me if you know it")
        elif len(tokens) == 2:
            add("SPLIT", record, record["full_name"],
                f"given=«{tokens[0]}» surname=«{tokens[1]}»", "safe split",
                changes={"first_name": tokens[0], "last_name": tokens[1],
                         "middle_name": ""})
        else:
            add("SPLIT3", record, record["full_name"],
                f"A) «{' '.join(tokens[:-1])}»+«{tokens[-1]}»   "
                f"B) «{' '.join(tokens[:-2])}»+«{' '.join(tokens[-2:])}»",
                "two surnames is the norm here, so usually B")

    # Several rules can match one card — a company tag and a two-word name, or
    # a rewrite and a split. They all write the same field, so the last one
    # applied wins and silently undoes the others. Only the most specific is
    # kept, and the rest are dropped rather than offered.
    # CLASH is in the list so a fact the owner gave settles it: «Emilio bq» with
    # the company MásMóvil is a decision, not a conflict to be raised again on
    # every run.
    precedence = ["KNOWN", "REWRITE", "ORG", "KINHEAD", "NFIELD", "FLIP", "KIN",
                  "SPLIT3", "SPLIT", "ASK", "CLASH"]
    best = {}
    for action in actions:
        if action["kind"] not in precedence:
            continue
        key = action["identity"]
        rank = precedence.index(action["kind"])
        if key not in best or rank < best[key][0]:
            best[key] = (rank, action["id"])
    keep = {action_id for _, action_id in best.values()}
    actions = [a for a in actions
               if a["kind"] not in precedence or a["id"] in keep]

    matched = vcard.match(secondary, primary)
    for record, hits in matched:
        # A hit whose name agrees is the same person; one that only shares a
        # number is a household, not a person. Dropping the agreeing ones from
        # the import without offering a merge loses everything the secondary
        # book held for them — emails, notes, addresses.
        agreeing = [h for h in hits if h[2]]
        if len(agreeing) == 1:
            target = agreeing[0][0]
            have_tel = {vcard.phone_key(p) for p in target["phones"]}
            have_mail = {m.lower() for m in target["emails"]}
            new_tel = [[label, vcard.normalize_phone(value, prefix, length)]
                       for label, value in record["phone_labels"]
                       if vcard.phone_key(value) not in have_tel]
            new_mail = [[label, value] for label, value in record["email_labels"]
                        if value.lower() not in have_mail]
            new_extras = {k: v for k, v in record["extras"].items()
                          if k not in target["extras"]}
            # An address the import would refuse to write is not missing data.
            # Comparing on the field's presence proposed re-adding exactly the
            # junk that had been decided against.
            if "ADR" in new_extras:
                kept = [v for v in new_extras["ADR"] if vcard.readable_address(v)]
                if kept:
                    new_extras["ADR"] = kept
                else:
                    del new_extras["ADR"]
            if not (new_tel or new_mail or new_extras):
                continue
            summary = " · ".join(
                part for part in (
                    f"tel+{new_tel}" if new_tel else "",
                    f"mail+{new_mail}" if new_mail else "",
                    f"{'/'.join(new_extras)}+{list(new_extras.values())}" if new_extras else "",
                ) if part)
            add("MERGE", record,
                f"«{record['full_name']}» already exists as «{target['full_name']}»",
                f"add to the existing card · {summary}",
                f"{len(record['phones']) - len(new_tel)} number(s) and "
                f"{len(record['emails']) - len(new_mail)} address(es) already there; "
                "each keeps the label it had",
                changes={"merge_into": target.get("apple_id", ""),
                         "add_phones": new_tel, "add_emails": new_mail,
                         "add_extras": new_extras})
        elif len(hits) > 1 or (hits and not agreeing):
            add("CLASH", record, f"matches {[h[0]['full_name'] for h in hits]}",
                "which one is the same person?",
                "a shared household landline matches people who are not the same")
            # And offer the import as well. A clash says «I cannot tell», not
            # «do not migrate»: answering that these are different people left
            # the record out of the book entirely, silently, because no import
            # was ever proposed for it.
            if record["phones"] or record["emails"]:
                add("IMPORT", record,
                    f"tel={record['phones'] or '—'} mail={record['emails'] or '—'}",
                    "create as a separate card, if the clash says they are not the same",
                    "answer this too: refusing the clash alone does not migrate anything",
                    changes={"phone_labels": [
                        [label, vcard.normalize_phone(value, prefix, length)]
                        for label, value in record["phone_labels"]]})
        elif not hits and (record["phones"] or record["emails"]):
            carried = {
                "tel": [f"{label or 'otro'}:{vcard.normalize_phone(value, prefix, length)}"
                        for label, value in record["phone_labels"]],
                "mail": [f"{label or 'otro'}:{value}" for label, value in record["email_labels"]],
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
                f"create · {summary}",
                changes={"phone_labels": [
                    [label, vcard.normalize_phone(value, prefix, length)]
                    for label, value in record["phone_labels"]]})
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
