import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vcard  # noqa: E402


def _card(name, phones=(), emails=()):
    return {
        "full_name": name,
        "phone_keys": [k for k in (vcard.phone_key(p) for p in phones) if k],
        "emails": list(emails),
        "name_key": vcard.strip_accents(name),
    }


class TestParse:
    def test_applescript_comma_separator_does_not_swallow_cards(self):
        # AppleScript joins a list of vcards with ", ", leaving every BEGIN
        # after the first in mid-line. Splitting naively finds only one card.
        payload = (
            "BEGIN:VCARD\r\nN:Uno;A;;;\r\nEND:VCARD\r\n, "
            "BEGIN:VCARD\r\nN:Dos;B;;;\r\nEND:VCARD\r\n"
        )
        assert len(vcard.parse(payload)) == 2

    def test_folded_lines_are_unfolded(self):
        payload = "BEGIN:VCARD\r\nNOTE:one\r\n two\r\nEND:VCARD\r\n"
        assert vcard.parse(payload)[0]["NOTE"][0][1] == "onetwo"

    def test_only_the_folding_space_is_removed(self):
        # RFC 6350 folds with exactly one space; a second one is content.
        payload = "BEGIN:VCARD\r\nNOTE:one\r\n  two\r\nEND:VCARD\r\n"
        assert vcard.parse(payload)[0]["NOTE"][0][1] == "one two"

    def test_empty_payload_is_no_cards(self):
        assert vcard.parse("") == []


class TestPhones:
    def test_local_length_gets_the_country_prefix(self):
        assert vcard.normalize_phone("628457303") == "+34628457303"

    def test_double_zero_becomes_plus(self):
        assert vcard.normalize_phone("0044 20 7946 0958") == "+442079460958"

    def test_already_international_is_untouched(self):
        assert vcard.normalize_phone("+1 (646) 450-5304") == "+16464505304"

    def test_invisible_bidi_controls_are_stripped(self):
        assert vcard.normalize_phone("‪+34 722 69 00 23‬") == "+34722690023"

    def test_key_collides_across_prefixed_and_bare(self):
        assert vcard.phone_key("+34628457303") == vcard.phone_key("628457303")

    def test_blanket_prefix_flags_a_foreign_number_of_local_length(self):
        safe, offenders = vcard.blanket_prefix_safe(["628457303", "212345678"])
        assert not safe and offenders == ["212345678"]

    def test_blanket_prefix_safe_when_every_number_fits(self):
        safe, offenders = vcard.blanket_prefix_safe(["628457303", "919311062"])
        assert safe and offenders == []


class TestMatching:
    def test_household_landline_is_reported_as_shared(self):
        people = [
            _card("Alfonso", ["913062058"]),
            _card("Ire", ["913062058"]),
            _card("Tere", ["913062058"]),
        ]
        assert vcard.shared_numbers(people) == {"913062058"}

    def test_a_number_used_by_one_person_twice_is_not_shared(self):
        people = [_card("Alfonso", ["913062058", "913062058"])]
        assert vcard.shared_numbers(people) == set()

    def test_shared_number_hit_is_flagged_and_name_disagreement_reported(self):
        source = [_card("Patricia Morales", ["608724453", "919311062"])]
        target = [
            _card("Patricia Morales", ["608724453"]),
            _card("Jorge Lillo", ["919311062"]),
        ]
        # both records are in the same household, so the landline is shared
        target[1]["phone_keys"].append(vcard.phone_key("919311062"))
        _, hits = vcard.match(source, target)[0]
        agreement = {h[0]["full_name"]: h[2] for h in hits}
        assert agreement["Patricia Morales"] is True
        assert agreement["Jorge Lillo"] is False

    def test_name_match_only_applies_when_no_phone_or_email_hit(self):
        source = [_card("Alberto Mercado")]
        target = [_card("Alberto Mercado")]
        _, hits = vcard.match(source, target)[0]
        assert [h[1] for h in hits] == ["name"]

    def test_no_hit_leaves_the_record_unmatched(self):
        _, hits = vcard.match([_card("Nadie", ["600000000"])], [_card("Otro")])[0]
        assert hits == []


class TestNames:
    def test_google_inverted_name_is_flipped(self):
        assert vcard.flip_inverted("Mancheño, Ire") == "Ire Mancheño"

    def test_a_plain_name_is_left_alone(self):
        assert vcard.flip_inverted("Ire Mancheño") == "Ire Mancheño"

    def test_trailing_kinship_word_is_detected(self):
        assert vcard.relationship_at_end("miriam prima")

    def test_leading_kinship_word_is_not_the_minority_form(self):
        assert not vcard.relationship_at_end("Tía Adelina")

    def test_accented_kinship_word_is_detected(self):
        assert vcard.relationship_at_end("Juan Carlos Tío")


class TestPretty:
    def test_lowercase_word_is_capitalised(self):
        assert vcard.pretty("bea") == "Bea"

    def test_owner_supplied_spelling_wins(self):
        assert vcard.pretty("sofia", {"sofia": "Sofía"}) == "Sofía"

    def test_an_already_capitalised_word_is_left_alone(self):
        assert vcard.pretty("McDonald") == "McDonald"


class TestQueueContract:
    def test_every_kind_the_builder_emits_is_known_to_the_reviewer(self):
        # An unknown kind used to crash the reviewer with a KeyError, which
        # hides the whole block instead of showing it.
        import ast
        import pathlib

        here = pathlib.Path(__file__).resolve().parent.parent
        emitted = set()
        tree = ast.parse((here / "audit.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            is_add = isinstance(node, ast.Call) and getattr(node.func, "id", "") == "add"
            if is_add and node.args and isinstance(node.args[0], ast.Constant):
                emitted.add(node.args[0].value)
        source = (here / "review.py").read_text(encoding="utf-8")
        known = set(ast.literal_eval(source.split("ORDER = ", 1)[1].split("\nTITLES", 1)[0]))
        assert emitted <= known, f"reviewer does not know: {sorted(emitted - known)}"


class TestEmptyCards:
    def test_a_card_with_only_a_name_is_proposed_for_deletion(self):
        import audit

        record = {"source": "s", "index": 0, "ref": "s#0", "full_name": "Ana",
                  "given": "", "surname": "", "organisation": "", "phones": [],
                  "emails": [], "phone_keys": [], "name_key": "ana", "uid": "",
                  "extras": {}}
        actions = audit.build([record], [], {})
        empty = [a for a in actions if a["kind"] == "EMPTY"]
        assert len(empty) == 1 and "holds" not in empty[0]["note"]

    def test_a_note_the_deletion_would_lose_is_named_in_the_action(self):
        import audit

        record = {"source": "s", "index": 0, "ref": "s#0", "full_name": "Ana",
                  "given": "", "surname": "", "organisation": "", "phones": [],
                  "emails": [], "phone_keys": [], "name_key": "ana", "uid": "",
                  "extras": {"NOTE": ["Torrelavega 3 C"]}}
        empty = [a for a in audit.build([record], [], {}) if a["kind"] == "EMPTY"]
        assert "Torrelavega 3 C" in empty[0]["note"]


class TestGroupedProperties:
    def test_a_grouped_property_is_read_under_its_real_name(self):
        # Apple writes «item1.TEL» whenever the number carries a custom label.
        # Reading the prefixed form as the name loses the number entirely.
        payload = (
            "BEGIN:VCARD\r\nFN:Javi\r\n"
            "item1.TEL;type=pref:+34616475528\r\n"
            "item1.X-ABLabel:Móvil\r\nEND:VCARD\r\n"
        )
        card = vcard.parse(payload)[0]
        assert [v for _, v in card["TEL"]] == ["+34616475528"]

    def test_the_group_prefix_survives_in_the_raw_head_for_labels(self):
        payload = "BEGIN:VCARD\r\nitem1.TEL:+34616475528\r\nEND:VCARD\r\n"
        assert vcard.parse(payload)[0]["TEL"][0][0] == "item1.TEL"

    def test_grouped_and_plain_properties_land_together(self):
        payload = (
            "BEGIN:VCARD\r\nTEL;type=HOME:919311062\r\n"
            "item1.TEL;type=pref:+34616475528\r\nEND:VCARD\r\n"
        )
        assert len(vcard.parse(payload)[0]["TEL"]) == 2


class TestImportCarriesEverything:
    def test_a_note_holding_an_address_is_carried_into_the_import(self):
        import audit

        record = {"source": "g", "index": 0, "ref": "g#0", "full_name": "Ana",
                  "given": "", "surname": "", "organisation": "", "phones": ["600111222"],
                  "emails": [], "phone_keys": ["600111222"], "name_key": "ana", "uid": "",
                  "extras": {"NOTE": ["Torrelavega 3 C"]}}
        imports = [a for a in audit.build([], [record], {}) if a["kind"] == "IMPORT"]
        assert "Torrelavega 3 C" in imports[0]["after"]

    def test_the_before_names_the_extra_fields_so_nothing_is_silent(self):
        import audit

        record = {"source": "g", "index": 0, "ref": "g#0", "full_name": "Ana",
                  "given": "", "surname": "", "organisation": "", "phones": ["600111222"],
                  "emails": [], "phone_keys": ["600111222"], "name_key": "ana", "uid": "",
                  "extras": {"ADR": [";;Calle X;Madrid;;;"]}}
        imports = [a for a in audit.build([], [record], {}) if a["kind"] == "IMPORT"]
        assert "ADR" in imports[0]["before"]


class TestLocalCards:
    def test_a_card_without_uid_or_category_is_flagged_local(self):
        import audit
        import tempfile

        payload = (
            "BEGIN:VCARD\r\nFN:Apple España SA\r\nORG:Apple España SA;\r\n"
            "X-ABUID:C2D26598-6F59-460B-B6A6-D026551C6687:ABPerson\r\nEND:VCARD\r\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vcf", delete=False,
                                         encoding="utf-8") as handle:
            handle.write(payload)
        record = audit.load_records(handle.name, "icloud")[0]
        assert record["local_only"]
        assert record["apple_id"] == "C2D26598-6F59-460B-B6A6-D026551C6687:ABPerson"

    def test_a_synced_card_is_not_flagged(self):
        import audit
        import tempfile

        payload = (
            "BEGIN:VCARD\r\nFN:Javi\r\nCATEGORIES:card\r\n"
            "UID:DC997E23-D97D-4E90-B00B-E9FD4F7771E7\r\n"
            "X-ABUID:BA84EE53-DFC2-4A13-969D-850D0ADAB3DB:ABPerson\r\nEND:VCARD\r\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".vcf", delete=False,
                                         encoding="utf-8") as handle:
            handle.write(payload)
        assert not audit.load_records(handle.name, "icloud")[0]["local_only"]

    def test_a_card_from_another_exporter_is_never_called_local(self):
        import audit
        import tempfile

        # A Google export carries neither UID nor CATEGORIES either; calling
        # it «local to this Mac» would be nonsense.
        payload = "BEGIN:VCARD\r\nFN:Rodrigo\r\nORG:bq\r\nEND:VCARD\r\n"
        with tempfile.NamedTemporaryFile("w", suffix=".vcf", delete=False,
                                         encoding="utf-8") as handle:
            handle.write(payload)
        assert not audit.load_records(handle.name, "gmail")[0]["local_only"]


class TestStructuredName:
    def _record(self, full, surname, given, middle):
        return {"source": "i", "index": 0, "ref": "i#0", "full_name": full,
                "given": given, "surname": surname, "middle": middle,
                "organisation": "", "phones": ["600111222"], "emails": [],
                "phone_keys": ["600111222"], "name_key": full.lower(), "uid": "",
                "apple_id": "", "local_only": False, "extras": {}}

    def test_a_company_in_the_surname_slot_is_reported(self):
        import audit

        record = self._record("Javi Griñan <Accenture>", "<Accenture>", "Javi", "Griñan")
        found = [a for a in audit.build([record], [], {}) if a["kind"] == "NFIELD"]
        assert found and "given=«Javi» surname=«Griñan»" in found[0]["after"]

    def test_a_well_formed_name_produces_nothing(self):
        import audit

        record = self._record("Jorge Lillo Cobacho", "Lillo Cobacho", "Jorge", "")
        assert not [a for a in audit.build([record], [], {}) if a["kind"] == "NFIELD"]


class TestStableIdentity:
    def test_the_id_survives_a_card_being_deleted_before_it(self):
        import audit

        # Deleting one card shifts every ref after it. An id built on the ref
        # would move with it and point a saved decision at someone else.
        def record(index, apple_id):
            return {"source": "icloud", "index": index, "ref": f"icloud#{index}",
                    "full_name": "Ana", "given": "", "surname": "", "middle": "",
                    "organisation": "", "phones": [], "emails": [], "phone_keys": [],
                    "name_key": "ana", "uid": "", "apple_id": apple_id,
                    "local_only": False, "extras": {}}

        before = audit.build([record(39, "AAA:ABPerson")], [], {})[0]["id"]
        after = audit.build([record(12, "AAA:ABPerson")], [], {})[0]["id"]
        assert before == after

    def test_a_book_without_apple_ids_is_keyed_on_its_content(self):
        import audit

        base = {"source": "gmail", "index": 0, "ref": "gmail#0", "full_name": "Ana",
                "given": "", "surname": "", "middle": "", "organisation": "",
                "phones": ["600111222"], "emails": [], "phone_keys": ["600111222"],
                "name_key": "ana", "uid": "", "apple_id": "", "local_only": False,
                "extras": {}}
        moved = dict(base, index=7, ref="gmail#7")
        assert audit.identity(base) == audit.identity(moved)


class TestPersonScript:
    def _script(self, **overrides):
        import apply

        record = {"given": "Ana", "surname": "Ruiz", "full_name": "Ana Ruiz",
                  "organisation": "", "phones": [], "emails": [], "extras": {}}
        record.update(overrides)
        return apply.build_person_script(record)

    def test_a_quote_in_a_note_cannot_break_out_of_the_string(self):
        # An unescaped quote turns a create into a syntax error at best, and
        # into a different command at worst.
        script = self._script(extras={"NOTE": ['dijo "hola" y se fue']})
        assert '\\"hola\\"' in script
        assert script.count('set note of p to "') == 1

    def test_a_backslash_is_escaped_before_the_quotes(self):
        script = self._script(surname="O\\Brien")
        assert "O\\\\Brien" in script

    def test_every_phone_and_email_is_created(self):
        script = self._script(phones=["+34600111222", "+34911111111"],
                              emails=["a@example.com"])
        assert script.count("make new phone") == 2
        assert script.count("make new email") == 1

    def test_the_script_returns_the_new_id_so_it_can_be_undone(self):
        assert "return id of p" in self._script()

    def test_a_card_with_no_organisation_sets_none(self):
        assert "set organization" not in self._script()


class TestEditScript:
    def test_only_the_named_fields_are_written(self):
        import apply

        # A change that mentions the name must not blank the organisation.
        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.write_fields("X:ABPerson", {"first_name": "Bea (Irene)"})
        assert "set first name" in calls[0]
        assert "set organization" not in calls[0]
        assert "set last name" not in calls[0]

    def test_a_quote_in_a_value_is_escaped(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.write_fields("X:ABPerson", {"first_name": 'Bar "El Rincón"'})
        assert '\\"El Rincón\\"' in calls[0]

    def test_the_card_is_saved_after_writing(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.write_fields("X:ABPerson", {"organisation": "Mi Casita Guarde"})
        assert calls[0].strip().endswith("end tell")
        assert "save" in calls[0]


class TestMissingValue:
    def test_an_empty_field_reads_as_empty_not_as_the_literal(self):
        import apply

        apply.osascript = lambda body: "Bea|missing value|missing value"
        assert apply.read_fields("X:ABPerson") == {
            "first_name": "Bea", "last_name": "", "organisation": ""}
