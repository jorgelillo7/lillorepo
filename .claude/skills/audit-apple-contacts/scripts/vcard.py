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
            name = head.split(";")[0].upper()
            # A property may carry a group prefix («item1.TEL»), which Apple
            # uses whenever a custom label is attached. Reading the prefixed
            # form as the property name silently drops the value.
            if "." in name:
                name = name.split(".", 1)[1]
            props[name].append((head, value))
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


_SHARED = {"primo", "prima", "tio", "tia", "madre", "padre", "abuelo", "abuela",
           "hermano", "hermana", "amigo", "amiga", "vecino", "vecina", "taller",
           "karate", "tienda", "trabajo", "guardias", "movil"}


def name_tokens(name):
    """Tokens that identify a person, for judging whether two names agree.

    A relationship word is not one of them. Once «Primo Guille» and «Primo Juan
    Carlos» are both in the book, sharing «primo» is not evidence they are the
    same person — and it was enough to make every cousin match every other.
    """
    tokens = {t for t in re.split(r"\W+", strip_accents(name)) if len(t) > 2}
    return tokens - _SHARED


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


def labelled(props, name):
    """Values of a property with the label each one carries.

    Apple stores a custom label in a sibling «group.X-ABLabel» line, while a
    plain vCard uses TYPE parameters. Reading only the value throws the label
    away, and then an import invents one — a work number becomes «home» and
    nobody notices until they call it.
    """
    groups = {head.split(".", 1)[0]: value
              for head, value in props.get("X-ABLABEL", [])
              if "." in head}
    out = []
    for head, value in props.get(name, []):
        group = head.split(".", 1)[0] if "." in head else None
        if group and group in groups:
            label = groups[group].strip()
        else:
            types = re.findall(r"type=([A-Za-z]+)", head, re.I)
            types = [t for t in types if t.lower() not in ("pref", "internet", "voice")]
            label = types[0].lower() if types else ""
        out.append((_APPLE_LABELS.get(label.lower(), label), value))
    return out


_APPLE_LABELS = {
    "cell": "móvil", "iphone": "iPhone", "home": "casa", "work": "trabajo",
    "main": "principal", "other": "otro", "fax": "fax",
    "_$!<home>!$_": "casa", "_$!<work>!$_": "trabajo", "_$!<mobile>!$_": "móvil",
    "_$!<homepage>!$_": "página web", "_$!<other>!$_": "otro",
}


def unescape(value):
    """Undo vCard escaping. A URL arrives as «http\\://…» and must not be
    stored with the backslash."""
    return re.sub(r"\\([\\,;:nN])",
                  lambda m: "\n" if m.group(1) in "nN" else m.group(1), value or "")


_STREET = re.compile(r"\d|\bcalle\b|\bavda\b|\bavenida\b|\bcamino\b|\bplaza\b"
                     r"|\bpaseo\b|\bc/|\bstreet\b|\broad\b|\bvia\b", re.I)


def readable_address(value):
    """The human-readable line of an ADR, or None when it holds no street.

    Google exports the components in the wrong slots and repeats a readable
    form in the last one. Many carry only a town, which says nothing the card
    does not already say; those are not worth importing. One that names a
    street is real data and is the only record of it.
    """
    parts = [p.strip() for p in unescape(value or "").split(";") if p.strip()]
    if not parts or not _STREET.search(" ".join(parts)):
        return None
    return parts[-1]
