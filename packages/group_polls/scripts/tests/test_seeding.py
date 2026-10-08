"""The seed questions are valid polls and go out in order, once."""

import json
import re
from pathlib import Path

import pytest

from packages.group_polls.scripts.seeding import (
    load,
    new_code,
    next_batch,
    poll_document,
)

SEED = Path(__file__).resolve().parents[2] / "seed" / "questions.json"


def test_every_seed_question_fits_the_app_limits():
    questions = load(json.loads(SEED.read_text()))
    assert len(questions) == 50
    texts = [q["es"][0].lower() for q in questions]
    assert len(set(texts)) == len(texts)


def test_invalid_entries_are_named():
    bad = {"questions": [{"es": ["¿A o a?", "A", "a"], "en": ["A or B?", "A", "B"]}]}
    with pytest.raises(ValueError, match="#0 es: same answers"):
        load(bad)


def test_batches_skip_published_questions():
    qs = [{"n": i} for i in range(5)]
    assert [i for i, _ in next_batch(qs, {0, 2}, 2)] == [1, 3]


def test_documents_match_the_app_schema():
    code, doc = poll_document({"es": ["¿Café o té?", "Café", "Té"]}, "es")
    assert re.fullmatch(r"[a-km-np-zA-HJ-NP-Z2-9]{12}", code)
    assert doc["visibility"] == "public" and doc["durationDays"] == 7
    assert doc["redVotes"] == doc["blueVotes"] == doc["reports"] == 0
    assert new_code() != new_code()
