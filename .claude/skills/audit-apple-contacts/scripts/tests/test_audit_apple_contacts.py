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

        # The tag is preserved, not stripped: it is often the only thing
        # identifying the card, and it is read from the list.
        record = self._record("Javi Griñan <Accenture>", "<Accenture>", "Javi", "Griñan")
        found = [a for a in audit.build([record], [], {}) if a["kind"] == "NFIELD"]
        assert found
        assert found[0]["changes"]["first_name"] == "Javi Griñan <Accenture>"
        assert found[0]["changes"]["last_name"] == ""

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

        apply.osascript = lambda body: "Bea|missing value|missing value|missing value"
        assert apply.read_fields("X:ABPerson") == {
            "first_name": "Bea", "last_name": "", "organisation": "",
            "middle_name": ""}


class TestOneWritePerField:
    def _card(self, full, surname="", given="", middle="", org=""):
        return {"source": "icloud", "index": 0, "ref": "icloud#0", "full_name": full,
                "given": given, "surname": surname, "middle": middle,
                "organisation": org, "phones": ["600111222"], "emails": [],
                "phone_keys": ["600111222"], "name_key": full.lower(), "uid": "",
                "apple_id": "A:ABPerson", "local_only": False, "extras": {}}

    def test_a_company_tag_and_a_two_word_name_yield_one_action(self):
        import audit

        # Both rules match «julio bq»: the company tag and the two-word split.
        # They write the same field, so the second applied would undo the first.
        config = {"organisations": {r"\bbq\b": "bq"}}
        actions = audit.build([self._card("julio bq")], [], config)
        naming = [a for a in actions
                  if a["kind"] in {"ORG", "SPLIT", "SPLIT3", "NFIELD", "KIN", "FLIP"}]
        assert len(naming) == 1 and naming[0]["kind"] == "ORG"

    def test_the_emptied_brackets_do_not_survive_the_company_removal(self):
        import audit

        config = {"organisations": {r"\baccenture\b": "Accenture"}}
        actions = audit.build([self._card("Javi Griñan <Accenture>")], [], config)
        org = [a for a in actions if a["kind"] == "ORG"][0]
        assert "«Javi Griñan»" in org["after"]
        assert "<>" not in org["after"] and "()" not in org["after"]

    def test_a_phone_action_is_not_dropped_by_a_naming_action(self):
        import audit

        config = {"organisations": {r"\bbq\b": "bq"}}
        kinds = {a["kind"] for a in audit.build([self._card("julio bq")], [], config)}
        assert "PHONE" in kinds


class TestTagStaysVisible:
    def _card(self, full, surname, given, middle=""):
        return {"source": "icloud", "index": 0, "ref": "icloud#0", "full_name": full,
                "given": given, "surname": surname, "middle": middle,
                "organisation": "", "phones": ["600111222"], "emails": [],
                "phone_keys": ["600111222"], "name_key": full.lower(), "uid": "",
                "apple_id": "A:ABPerson", "local_only": False, "extras": {}}

    def test_the_displayed_name_is_not_changed_only_its_field(self):
        import audit

        # «(rebe)» may be the only thing that identifies this Rober. Dropping
        # it, or moving it to a note, removes it from the list where it is read.
        record = self._card("Rober (rebe)", "(rebe)", "Rober")
        action = [a for a in audit.build([record], [], {}) if a["kind"] == "NFIELD"][0]
        assert action["changes"]["first_name"] == "Rober (rebe)"
        assert action["changes"]["last_name"] == ""

    def test_the_middle_name_is_cleared_so_it_is_not_shown_twice(self):
        import audit

        record = self._card("Peluquería Sebastián Martín (Dehesa)", "(Dehesa)",
                            "Peluquería Sebastián", "Martín")
        action = [a for a in audit.build([record], [], {}) if a["kind"] == "NFIELD"][0]
        assert action["changes"]["middle_name"] == ""

    def test_the_middle_name_is_written_when_asked(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.write_fields("X:ABPerson", {"middle_name": ""})
        assert "set middle name" in calls[0]


class TestEditIsAnApproval:
    ACTIONS = {"a": {"id": "a", "kind": "NFIELD"}, "b": {"id": "b", "kind": "NFIELD"},
               "c": {"id": "c", "kind": "NFIELD"}, "d": {"id": "d", "kind": "PHONE"}}

    def test_a_corrected_proposal_counts_as_approved(self):
        # «edit» is the owner overriding the proposal — the answer they took
        # most care over. Accepting only «yes» discards it silently.
        import apply

        decisions = {"a": {"verdict": "yes"}, "b": {"verdict": "edit", "value": "{}"}}
        got = apply.approved_actions(self.ACTIONS, decisions, "NFIELD")
        assert {x["id"] for x in got} == {"a", "b"}

    def test_a_refusal_and_an_unknown_are_left_out(self):
        import apply

        decisions = {"a": {"verdict": "no"}, "b": {"verdict": "unknown"},
                     "c": {"verdict": "yes"}}
        got = apply.approved_actions(self.ACTIONS, decisions, "NFIELD")
        assert [x["id"] for x in got] == ["c"]

    def test_another_kind_is_not_picked_up(self):
        import apply

        decisions = {"d": {"verdict": "yes"}}
        assert apply.approved_actions(self.ACTIONS, decisions, "NFIELD") == []


class TestOwnerFacts:
    def _card(self, full, org=""):
        return {"source": "icloud", "index": 0, "ref": "icloud#0", "full_name": full,
                "given": full, "surname": "", "middle": "", "organisation": org,
                "phones": ["600111222"], "emails": [], "phone_keys": ["600111222"],
                "name_key": full.lower(), "uid": "", "apple_id": "A:ABPerson",
                "local_only": False, "extras": {}}

    def test_a_fact_outranks_every_guess(self):
        import audit

        # A rule guesses; the owner does not. «julio bq» would otherwise get a
        # company action that leaves the surname unknown.
        config = {"organisations": {r"\bbq\b": "bq"},
                  "known": [{"name": "julio bq", "given": "julio",
                             "surname": "gonzalez", "organisation": "bq"}]}
        actions = audit.build([self._card("julio bq")], [], config)
        naming = [a for a in actions if a["kind"] in {"KNOWN", "ORG", "SPLIT"}]
        assert len(naming) == 1 and naming[0]["kind"] == "KNOWN"
        assert naming[0]["changes"]["last_name"] == "gonzalez"

    def test_a_fact_reaches_a_card_no_rule_would_touch(self):
        import audit

        # A card with an organisation already set is skipped by the split rule,
        # so a missing surname there is otherwise never offered for fixing.
        config = {"known": [{"name": "juan carlos", "given": "Juan Carlos",
                             "surname": "Rico"}]}
        actions = audit.build([self._card("juan carlos", org="oracle")], [], config)
        assert [a["kind"] for a in actions if a["kind"] == "KNOWN"] == ["KNOWN"]

    def test_a_fact_matches_regardless_of_accents_and_case(self):
        import audit

        config = {"known": [{"name": "JAVI GRIÑAN <ACCENTURE>", "given": "Javi",
                             "surname": "Griñan"}]}
        actions = audit.build([self._card("Javi Griñan <Accenture>")], [], config)
        assert any(a["kind"] == "KNOWN" for a in actions)


class TestPhoneTargeting:
    def test_the_number_is_found_despite_spaces_and_controls(self):
        import apply

        phones = ["+34 628 45 73 03", "‪+34919311062‬"]
        assert apply.find_phone_index(phones, "919311062") == 2

    def test_a_prefixed_and_a_bare_form_are_the_same_number(self):
        import apply

        assert apply.find_phone_index(["+34628457303"], "628457303") == 1

    def test_two_identical_numbers_are_refused_rather_than_guessed(self):
        import apply

        # Editing the wrong element of a card with several numbers is worse
        # than doing nothing, so an ambiguous match is not resolved.
        assert apply.find_phone_index(["600111222", "600 111 222"], "600111222") is None

    def test_a_number_that_is_not_there_returns_nothing(self):
        import apply

        assert apply.find_phone_index(["600111222"], "699999999") is None

    def test_the_label_is_never_part_of_the_rewrite(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.write_phone_value("X:ABPerson", 2, "+34600111222")
        assert "set value of phone 2" in calls[0]
        assert "label" not in calls[0]


class TestMergeCarriesEverything:
    def test_a_url_is_written_and_unescaped(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.merge_into("X:ABPerson", {"add_extras": {"URL": ["http\\://example.com"]}})
        assert "make new url" in calls[0]
        assert "http://example.com" in calls[0]

    def test_a_field_it_cannot_write_is_reported_not_dropped(self):
        import apply

        apply.osascript = lambda body: ""
        left = apply.merge_into("X:ABPerson", {"add_extras": {"BDAY": ["1980-01-01"]}})
        assert left == {"BDAY": ["1980-01-01"]}

    def test_each_added_value_keeps_its_own_label(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.merge_into("X:ABPerson", {"add_phones": [["casa", "+34919311062"]],
                                        "add_emails": [["Personal", "a@b.com"]]})
        assert 'label:"casa"' in calls[0] and 'label:"Personal"' in calls[0]

    def test_a_value_with_no_label_gets_a_neutral_one(self):
        import apply

        calls = []
        apply.osascript = lambda body: calls.append(body) or ""
        apply.merge_into("X:ABPerson", {"add_emails": [["", "a@b.com"]]})
        assert 'label:"otro"' in calls[0]


class TestCreateCarriesEverything:
    def _record(self, **overrides):
        record = {"given": "Ana", "surname": "Ruiz", "full_name": "Ana Ruiz",
                  "organisation": "", "phones": [], "emails": [], "extras": {},
                  "phone_labels": [], "email_labels": []}
        record.update(overrides)
        import apply

        return apply.build_person_script(record)

    def test_an_address_naming_a_street_is_kept_in_its_readable_form(self):
        # Reading the components by position invents a city called «España»,
        # so the readable line is used whole instead.
        script = self._record(extras={"ADR": ["37 Camino Perales;;M;;ES;Camino Perales 37"]})
        assert 'street:"Camino Perales 37"' in script
        assert "city:" not in script

    def test_a_birthday_becomes_a_real_date(self):
        script = self._record(extras={"BDAY": ["19910525"]})
        assert "set year of d to 1991" in script
        assert "set month of d to May" in script
        assert "set day of d to 25" in script

    def test_the_day_is_reset_before_the_month_is_set(self):
        # Setting the month while the day is 31 rolls into the next month.
        script = self._record(extras={"BDAY": ["19910525"]})
        assert script.index("set day of d to 1") < script.index("set month of d to")

    def test_a_malformed_birthday_is_skipped_not_guessed(self):
        assert "birth date" not in self._record(extras={"BDAY": ["1991"]})

    def test_labels_come_from_the_record(self):
        script = self._record(phone_labels=[["casa", "+34919311062"]],
                              email_labels=[["Personal", "a@b.com"]])
        assert 'label:"casa"' in script and 'label:"Personal"' in script

    def test_the_new_id_is_returned_so_the_creation_can_be_undone(self):
        assert "return id of p" in self._record()


class TestCreationFoldsInDecisions:
    def _record(self, **kw):
        base = {"identity": "g:1", "full_name": "X", "given": "", "middle": "",
                "surname": "", "organisation": "", "phones": [], "emails": [],
                "extras": {}, "phone_labels": [], "email_labels": []}
        base.update(kw)
        return base

    def test_the_first_surname_joins_the_family_name_not_the_given_one(self):
        import apply

        # «Álvaro | Gómez | Jiménez» is Álvaro Gómez Jiménez: two surnames, one
        # given name. Attaching Gómez to the given name keeps the text and
        # still gets the person's name wrong.
        record = self._record(given="Álvaro", middle="Gómez", surname="Jiménez")
        got = apply.creation_record(record, "g:1", {}, {})
        assert got["given"] == "Álvaro"
        assert got["surname"] == "Gómez Jiménez"

    def test_the_middle_name_is_not_dropped(self):
        import apply

        # Google puts the first surname there. Writing only given and family
        # loses it, and «Guevara» disappears from the middle of a name.
        record = self._record(given="Joaquín Miguel Ladrón de", middle="Guevara",
                              surname="Mesonero")
        got = apply.creation_record(record, "g:1", {}, {})
        assert got["given"] == "Joaquín Miguel Ladrón de"
        assert got["surname"] == "Guevara Mesonero"

    def test_an_approved_action_overrides_the_source_fields(self):
        import apply

        # Google made «MM» the surname. The company action already said what
        # this name should be, so creating it raw would undo that answer.
        record = self._record(given="Andrés", middle="Reyes", surname="MM")
        actions = {"a": {"id": "a", "identity": "g:1", "kind": "ORG",
                         "changes": {"first_name": "Andrés Reyes", "last_name": "",
                                     "organisation": "MásMóvil"}}}
        got = apply.creation_record(record, "g:1", actions, {"a": {"verdict": "yes"}})
        assert got["given"] == "Andrés Reyes"
        assert got["surname"] == ""
        assert got["organisation"] == "MásMóvil"

    def test_a_refused_action_does_not_apply(self):
        import apply

        record = self._record(given="Emilio", surname="Bq", organisation="MásMóvil")
        actions = {"a": {"id": "a", "identity": "g:1", "kind": "CLASH",
                         "changes": {"first_name": "Emilio"}}}
        got = apply.creation_record(record, "g:1", actions, {"a": {"verdict": "no"}})
        assert got["surname"] == "Bq"

    def test_a_correction_wins_over_the_proposal(self):
        import apply

        record = self._record(given="Alfonso")
        actions = {"a": {"id": "a", "identity": "g:1", "kind": "KNOWN",
                         "changes": {"first_name": "Alfonso"}}}
        decisions = {"a": {"verdict": "edit",
                           "value": '{"first_name": "Primo Alfonso", "last_name": "Mancheño"}'}}
        got = apply.creation_record(record, "g:1", actions, decisions)
        assert got["given"] == "Primo Alfonso" and got["surname"] == "Mancheño"


class TestCreatedNumbersAreNormalised:
    def test_a_created_card_does_not_arrive_unformatted(self):
        import apply

        record = {"identity": "g:1", "full_name": "Ana", "given": "Ana", "middle": "",
                  "surname": "", "organisation": "", "phones": ["916712918"],
                  "emails": [], "extras": {},
                  "phone_labels": [["casa", "916712918"]], "email_labels": []}
        actions = {"i": {"id": "i", "identity": "g:1", "kind": "IMPORT",
                         "changes": {"phone_labels": [["casa", "+34916712918"]]}}}
        got = apply.creation_record(record, "g:1", actions, {})
        assert got["phone_labels"] == [["casa", "+34916712918"]]

    def test_the_identity_comes_from_the_action_not_the_record(self):
        import apply

        # records.json has no identity field; matching on it silently found
        # nothing and every created card arrived unformatted.
        record = {"full_name": "Ana", "given": "Ana", "middle": "", "surname": "",
                  "organisation": "", "phones": ["916712918"], "emails": [],
                  "extras": {}, "phone_labels": [["casa", "916712918"]],
                  "email_labels": []}
        actions = {"i": {"id": "i", "identity": "g:1", "kind": "IMPORT",
                         "changes": {"phone_labels": [["casa", "+34916712918"]]}}}
        got = apply.creation_record(record, "g:1", actions, {})
        assert got["phone_labels"] == [["casa", "+34916712918"]]


class TestAddressesWorthKeeping:
    def test_a_town_only_entry_is_skipped(self):
        import vcard

        assert vcard.readable_address("coslada;;;España;coslada España") is None

    def test_an_entry_naming_a_street_is_kept_in_its_readable_form(self):
        import vcard

        got = vcard.readable_address("37 Camino Perales;;M;;ES;Camino Perales 37")
        assert got == "Camino Perales 37"

    def test_the_skipped_ones_do_not_reach_the_script(self):
        import apply

        record = {"given": "Ana", "surname": "", "full_name": "Ana", "organisation": "",
                  "phones": [], "emails": [], "phone_labels": [], "email_labels": [],
                  "extras": {"ADR": ["Madrid;;;España;Madrid España"]}}
        assert "make new address" not in apply.build_person_script(record)

    def test_an_imported_address_is_labelled_home_not_other(self):
        import apply

        record = {"given": "Ana", "surname": "", "full_name": "Ana", "organisation": "",
                  "phones": [], "emails": [], "phone_labels": [], "email_labels": [],
                  "extras": {"ADR": ["37 Camino Perales;;M;;ES;Camino Perales 37"]}}
        assert 'label:"casa"' in apply.build_person_script(record)


class TestKinshipLeadingTheName:
    def _card(self, full, given, surname):
        return {"source": "g", "index": 0, "ref": "g#0", "full_name": full,
                "given": given, "surname": surname, "middle": "", "organisation": "",
                "phones": ["600111222"], "emails": [], "phone_keys": ["600111222"],
                "name_key": full.lower(), "uid": "", "apple_id": "", "local_only": False,
                "extras": {}}

    KIN = {"kinship": "primo|prima|tio|tia|madre|padre|abuelo|abuela|hermano|hermana"}

    def test_the_relationship_does_not_become_the_given_name(self):
        import audit

        # «Prima María» is one label for one person, not a given name «Prima»
        # with the surname «María».
        record = self._card("Prima María", "Prima", "María")
        found = [a for a in audit.build([record], [], self.KIN) if a["kind"] == "KINHEAD"]
        assert found and found[0]["changes"]["first_name"] == "Prima María"
        assert found[0]["changes"]["last_name"] == ""

    def test_it_matches_without_the_accent(self):
        import audit

        record = self._card("Tia Conchi", "Tia", "Conchi")
        assert any(a["kind"] == "KINHEAD" for a in audit.build([record], [], self.KIN))

    def test_a_name_merely_containing_a_kinship_word_is_left_alone(self):
        import audit

        record = self._card("Primo Ricardo Tiago", "Primo Ricardo", "Tiago")
        found = [a for a in audit.build([record], [], self.KIN) if a["kind"] == "KINHEAD"]
        assert found  # it still leads, so it still applies

    def test_an_ordinary_name_produces_nothing(self):
        import audit

        record = self._card("Aurora Soria Magano", "Aurora", "Soria Magano")
        assert not [a for a in audit.build([record], [], self.KIN) if a["kind"] == "KINHEAD"]


class TestAgreementIgnoresSharedWords:
    def test_two_cousins_do_not_match_each_other(self):
        import vcard

        # Standardising on «Primo Nombre» gave every cousin a token in common,
        # which was enough to read as the same person.
        a = vcard.name_tokens("Primo Guille")
        b = vcard.name_tokens("Primo Juan Carlos")
        assert not (a & b)

    def test_a_real_name_still_matches_itself(self):
        import vcard

        assert vcard.name_tokens("Primo Guille") & vcard.name_tokens("Guille Primo")


class TestMergeDoesNotReAddRefusedData:
    def _pair(self, extras):
        source = {"source": "g", "index": 0, "ref": "g#0", "full_name": "Elena Garcia",
                  "given": "Elena", "surname": "Garcia", "middle": "", "organisation": "",
                  "phones": ["600111222"], "emails": [], "phone_keys": ["600111222"],
                  "name_key": "elena garcia", "uid": "", "apple_id": "",
                  "local_only": False, "extras": extras}
        target = dict(source, source="icloud", ref="icloud#0", apple_id="A:ABPerson",
                      extras={})
        return target, source

    def test_a_town_only_address_is_not_proposed_for_merging(self):
        import audit

        target, source = self._pair({"ADR": ["coslada;;;España;coslada España"]})
        assert not [a for a in audit.build([target], [source], {}) if a["kind"] == "MERGE"]

    def test_an_address_with_a_street_still_is(self):
        import audit

        target, source = self._pair({"ADR": ["37 Camino Perales;;M;;ES;Camino Perales 37"]})
        found = [a for a in audit.build([target], [source], {}) if a["kind"] == "MERGE"]
        assert found and found[0]["changes"]["add_extras"]["ADR"]


class TestDisplayNameFallback:
    def _record(self, **kw):
        base = {"identity": "g:1", "full_name": "", "given": "", "middle": "",
                "surname": "", "organisation": "", "phones": [], "emails": [],
                "extras": {}, "phone_labels": [], "email_labels": []}
        base.update(kw)
        return base

    def test_a_card_with_only_a_family_name_is_not_doubled(self):
        import apply

        # «Morata» in the family name and nothing in the given one came out as
        # «Morata Morata», because the fallback fired regardless.
        got = apply.creation_record(self._record(surname="Morata", full_name="Morata"),
                                    "g:1", {}, {})
        assert got["given"] == "" and got["surname"] == "Morata"

    def test_a_card_with_nothing_structured_still_uses_the_display_name(self):
        import apply

        got = apply.creation_record(self._record(full_name="Kano"), "g:1", {}, {})
        assert got["given"] == "Kano"


class TestNoteAfterMovingAnAddress:
    def test_the_moved_line_is_removed_and_the_rest_kept(self):
        import address

        note = "Calle Mercurio 74 bloque 1 3°C\nantigua:\nCalle David 7 4*8 Almería"
        assert address.note_without(note, [1]) == "antigua:\nCalle David 7 4*8 Almería"

    def test_several_lines_can_go_at_once(self):
        import address

        note = "C/ Arratia 20\n28802. Alcalá\nPlaza Mar Caspio\n1°A"
        assert address.note_without(note, [1, 2]) == "Plaza Mar Caspio\n1°A"

    def test_a_note_that_was_only_the_address_ends_up_empty(self):
        import address

        assert address.note_without("Torrelavega 3 C", [1]) == ""

    def test_blank_lines_left_at_the_edges_are_collapsed(self):
        import address

        # Removing the middle of «addr\n\nrest» must not leave a leading blank,
        # which some clients show as content and others as nothing.
        assert address.note_without("Calle X 1\n\nresto", [1]) == "resto"

    def test_nothing_is_dropped_when_no_lines_are_named(self):
        import address

        assert address.note_without("una\ndos", []) == "una\ndos"

    def test_blank_lines_do_not_take_a_number(self):
        import address

        # The reader numbers what they can see. Counting the raw lines removed
        # the blank between two entries and left the address in place.
        note = "6 C\n\nCalle Francisco Umbral 8\n\n25 campana"
        assert address.note_without(note, [2]) == "6 C\n\n\n25 campana"

    def test_the_last_visible_line_can_be_dropped(self):
        import address

        note = "uno\naparcar\n\ndos \ntres"
        assert address.note_without(note, [1, 3, 4]) == "aparcar"


class TestClashStillOffersTheImport:
    def _card(self, name, phones, source, apple_id=""):
        return {"source": source, "index": 0, "ref": f"{source}#0", "full_name": name,
                "given": name, "surname": "", "middle": "", "organisation": "",
                "phones": phones, "emails": [], "extras": {},
                "phone_labels": [["móvil", p] for p in phones], "email_labels": [],
                "phone_keys": [k for k in (vcard.phone_key(p) for p in phones) if k],
                "name_key": name.lower(), "uid": "", "apple_id": apple_id,
                "local_only": False}

    def test_a_household_landline_clash_does_not_drop_the_record(self):
        import audit

        # Four people share one landline. Saying «they are not the same» has to
        # leave a way to migrate them; before, it left them out of the book.
        target = [self._card("Tía Tere", ["913062058"], "icloud", "A:ABPerson")]
        source = [self._card("Alfonso", ["654235912", "913062058"], "gmail")]
        kinds = [a["kind"] for a in audit.build(target, source, {})]
        assert "CLASH" in kinds and "IMPORT" in kinds

    def test_a_clean_new_record_still_gets_one_import_only(self):
        import audit

        source = [self._card("Nadie", ["600111222"], "gmail")]
        kinds = [a["kind"] for a in audit.build([], source, {})]
        assert kinds.count("IMPORT") == 1 and "CLASH" not in kinds
