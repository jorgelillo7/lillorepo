"""Pure vCard logic: parsing, phone normalisation and cross-source matching.

No I/O and no AppleScript here, so every rule below is testable without a Mac.
"""

import collections
import re
import unicodedata

_REL_DEFAULT = (
    "primo|prima|tio|tia|madre|padre|abuelo|abuela|hermano|hermana|"
    "cunado|cunada|sobrino|sobrina|vecino|vecina"
)


def strip_accents(text):
    """Lowercase and drop diacritics, for comparisons only — never for storage."""
    decomposed = unicodedata.normalize("NFD", text or "")
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", plain).strip().lower()


def parse(text):
    """Parse a multi-vCard payload into a list of property dicts.

    Handles two shapes that break naive splitting: RFC folded lines (a
    continuation starts with space or tab), and the ", " that AppleScript
    inserts between items when a list of vcards is coerced to text — which
    leaves every BEGIN:VCARD after the first in mid-line.
    """
    text = (text or "").replace("\r\n", "\n")
    text = re.sub(r"\n[ \t]", "", text)
    text = text.replace("\n, BEGIN:VCARD", "\nBEGIN:VCARD")
    cards = []
    for chunk in text.split("BEGIN:VCARD")[1:]:
        body = chunk.split("END:VCARD")[0]
        props = collections.defaultdict(list)
        for line in body.split("\n"):
            if ":" not in line:
                continue
            head, value = line.split(":", 1)
            props[head.split(";")[0].upper()].append((head, value))
        cards.append(dict(props))
    return cards


def normalize_phone(raw, country_prefix="+34", local_length=9):
    """Return the number in international form, or unchanged if no rule fits."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+") and len(digits) == local_length:
        digits = country_prefix + digits
    return digits


def phone_key(raw, local_length=9):
    """Comparison key: the trailing local digits, so +34 X and X collide."""
    digits = re.sub(r"\D", "", normalize_phone(raw, local_length=local_length))
    return digits[-local_length:] if len(digits) >= local_length else None


def blanket_prefix_safe(numbers, local_length=9, local_first="6789"):
    """Check that adding the country prefix by length alone cannot be wrong.

    Returns (safe, offenders). A foreign number that happens to have the local
    length would silently acquire the wrong country, so this runs before any
    bulk rewrite rather than after.
    """
    offenders = []
    for raw in numbers:
        digits = re.sub(r"[^\d+]", "", raw or "")
        if digits.startswith("+") or digits.startswith("00"):
            continue
        if len(digits) != local_length or digits[:1] not in local_first:
            offenders.append(raw)
    return (not offenders), offenders


def shared_numbers(records):
    """Numbers used by more than one distinct name — household landlines.

    Matching on these produces false duplicates: four people in one house are
    not one person.
    """
    owners = collections.defaultdict(set)
    for record in records:
        for key in record.get("phone_keys", []):
            owners[key].add(strip_accents(record.get("full_name", "")))
    return {key for key, names in owners.items() if len(names) > 1}


def name_tokens(name):
    return {t for t in re.split(r"\W+", strip_accents(name)) if len(t) > 2}


def match(source, target):
    """Match each source record against target records.

    Every hit carries the reason and whether the names agree, because a phone
    hit alone is not evidence when the number is shared.
    """
    by_phone = collections.defaultdict(list)
    by_mail = collections.defaultdict(list)
    by_name = collections.defaultdict(list)
    for record in target:
        for key in record.get("phone_keys", []):
            by_phone[key].append(record)
        for mail in record.get("emails", []):
            by_mail[mail].append(record)
        if record.get("name_key"):
            by_name[record["name_key"]].append(record)

    shared = shared_numbers(list(source) + list(target))
    results = []
    for record in source:
        hits = []
        for key in record.get("phone_keys", []):
            for candidate in by_phone.get(key, []):
                reason = "phone" + (" (shared)" if key in shared else "")
                hits.append((candidate, reason))
        for mail in record.get("emails", []):
            for candidate in by_mail.get(mail, []):
                hits.append((candidate, "email"))
        if not hits and record.get("name_key"):
            for candidate in by_name.get(record["name_key"], []):
                hits.append((candidate, "name"))
        deduped = []
        for candidate, reason in hits:
            existing = [h for h in deduped if h[0] is candidate]
            if existing:
                continue
            agrees = bool(
                name_tokens(record.get("full_name", ""))
                & name_tokens(candidate.get("full_name", ""))
            )
            deduped.append((candidate, reason, agrees))
        results.append((record, deduped))
    return results


def flip_inverted(name):
    """«Surname, Given» → «Given Surname». Google exports use the first form."""
    if re.match(r"^[^,]+,\s*\S", name or ""):
        surname, given = [part.strip() for part in name.split(",", 1)]
        return f"{given} {surname}"
    return name


def relationship_at_end(name, vocabulary=_REL_DEFAULT):
    """True when the kinship word trails the name («Miriam prima»).

    The majority form in a real address book puts it first («Tía Adelina»), so
    this finds the minority to be flipped, not the other way round.
    """
    tokens = (name or "").split()
    if len(tokens) < 2:
        return False
    return bool(re.fullmatch(vocabulary, strip_accents(tokens[-1])))


def pretty(word, spelling=None):
    """Capitalise a name, applying any spelling the owner has corrected.

    Address books are full of lowercase, unaccented entries typed in a hurry.
    The map is supplied by the owner because inventing an accent is inventing
    data — «Jose» and «José» are both real names.
    """
    spelling = spelling or {}
    fixed = spelling.get(strip_accents(word))
    if fixed:
        return fixed
    return word.capitalize() if word.islower() else word
