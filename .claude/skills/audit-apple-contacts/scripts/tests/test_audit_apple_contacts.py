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
