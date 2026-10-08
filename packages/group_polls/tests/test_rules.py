"""Security rules of "¿Qué votáis?" against the Firestore emulator.

The Android app writes to Firestore directly, so these rules are the only boundary.
Skipped unless FIRESTORE_EMULATOR_HOST is set (CI has no emulator); how to run them:
OPERATIONS.md.
"""

import datetime as dt
from pathlib import Path

import pytest

from packages.group_polls.tests import emulator as fs
from packages.group_polls.tests.emulator import Increment, ServerTime

pytestmark = pytest.mark.skipif(
    not fs.HOST, reason="needs the Firestore emulator (FIRESTORE_EMULATOR_HOST)"
)

RULES = Path(__file__).resolve().parent.parent / "firestore.rules"
ANA, BEA, CARLOS, DANI = (fs.token(u) for u in ("ana", "bea", "carlos", "dani"))
PUBLIC, PRIVATE = "abcdefghijkm", "nopqrstuvwxy"


def poll_fields(creator="ana", visibility="public", **overrides) -> dict:
    fields = {
        "visibility": visibility,
        "question": "¿Playa o montaña?",
        "red": "Playa",
        "blue": "Montaña",
        "creatorId": creator,
        "creatorName": creator.capitalize(),
        "language": "es",
        "createdAt": ServerTime(),
        "durationDays": 7,
        "closedAt": None,
        "redVotes": 0,
        "blueVotes": 0,
        "reports": 0,
        "hidden": False,
    }
    fields.update(overrides)
    return fields


def vote(code, uid, side="red", name=None, counter=None, step=1):
    fields = {
        "voterId": uid,
        "side": side,
        "prediction": "blue",
        "votedAt": ServerTime(),
    }
    if name is not None:
        fields["name"] = name
    return (
        fs.create(f"polls/{code}/votes/{uid}", fields),
        fs.update(f"polls/{code}", {f"{counter or side}Votes": Increment(step)}),
    )


@pytest.fixture(autouse=True)
def fresh():
    fs.load_rules(RULES.read_text())
    fs.clear()
    assert fs.commit(fs.OWNER, fs.create(f"polls/{PUBLIC}", poll_fields()))
    assert fs.commit(
        fs.OWNER, fs.create(f"polls/{PRIVATE}", poll_fields(visibility="private"))
    )


# --- Creating ------------------------------------------------------------------------


def test_a_valid_poll_can_be_created():
    assert fs.commit(BEA, fs.create("polls/zzzzzzzzzzzz", poll_fields(creator="bea")))


@pytest.mark.parametrize(
    "overrides",
    [
        {"creatorId": "ana"},  # someone else's id
        {"redVotes": 5},  # pre-filled counters
        {"durationDays": 3},  # not 1, 7 or no limit
        {"hidden": True},
        {"question": "¿Sí?"},  # too short
        {"blue": "playa"},  # same answers
        {"createdAt": dt.datetime(2020, 1, 1, tzinfo=dt.UTC)},  # backdated
    ],
)
def test_invalid_polls_are_rejected(overrides):
    assert not fs.commit(
        BEA, fs.create("polls/zzzzzzzzzzzz", poll_fields(creator="bea", **overrides))
    )


def test_codes_must_look_random():
    assert not fs.commit(BEA, fs.create("polls/short", poll_fields(creator="bea")))
    assert not fs.commit(
        BEA, fs.create("polls/oooooooooooo", poll_fields(creator="bea"))
    )  # no o/O/0/1/l/I


def test_signed_out_users_cannot_read():
    assert not fs.get(None, f"polls/{PUBLIC}")
    assert fs.get(BEA, f"polls/{PRIVATE}")  # the code is the key


# --- Voting --------------------------------------------------------------------------


def test_one_vote_with_its_counter():
    assert fs.commit(BEA, *vote(PUBLIC, "bea"))
    assert fs.read(f"polls/{PUBLIC}")["redVotes"] == 1
    assert not fs.commit(BEA, *vote(PUBLIC, "bea", side="blue"))  # final


def test_vote_and_counter_must_go_together():
    assert not fs.commit(BEA, vote(PUBLIC, "bea")[0])  # vote without counter
    assert not fs.commit(BEA, vote(PUBLIC, "bea")[1])  # counter without vote
    assert not fs.commit(BEA, *vote(PUBLIC, "bea", counter="blue"))  # wrong counter
    assert not fs.commit(BEA, *vote(PUBLIC, "bea", step=2))  # +2


def test_cannot_vote_for_someone_else():
    assert not fs.commit(BEA, *vote(PUBLIC, "carlos"))


def test_names_only_on_private_polls():
    assert not fs.commit(BEA, *vote(PUBLIC, "bea", name="Bea"))
    assert fs.commit(BEA, *vote(PRIVATE, "bea", name="Bea"))


def test_who_voted_is_readable_only_on_private_polls():
    assert fs.commit(BEA, *vote(PUBLIC, "bea"))
    assert fs.commit(BEA, *vote(PRIVATE, "bea", name="Bea"))
    assert fs.query(CARLOS, "votes", [], parent=f"polls/{PRIVATE}")
    assert not fs.query(CARLOS, "votes", [], parent=f"polls/{PUBLIC}")
    assert fs.get(BEA, f"polls/{PUBLIC}/votes/bea")  # your own vote
    assert not fs.get(CARLOS, f"polls/{PUBLIC}/votes/bea")


def test_no_votes_once_closed_or_expired():
    assert not fs.commit(
        BEA, fs.update(f"polls/{PUBLIC}", {"closedAt": ServerTime()})
    )  # not the creator
    assert fs.commit(ANA, fs.update(f"polls/{PUBLIC}", {"closedAt": ServerTime()}))
    assert not fs.commit(BEA, *vote(PUBLIC, "bea"))
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=2)
    assert fs.commit(
        fs.OWNER,
        fs.create("polls/expiredpoll2", poll_fields(createdAt=old, durationDays=1)),
    )
    assert not fs.commit(BEA, *vote("expiredpoll2", "bea"))


def test_no_limit_polls_stay_open():
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=400)
    assert fs.commit(
        fs.OWNER,
        fs.create("polls/foreverpoll2", poll_fields(createdAt=old, durationDays=0)),
    )
    assert fs.commit(BEA, *vote("foreverpoll2", "bea"))


def test_polls_cannot_be_deleted_or_rewritten():
    assert not fs.commit(
        ANA, fs.update(f"polls/{PUBLIC}", {"question": "¿Otra pregunta?"})
    )
    assert not fs.commit(ANA, fs.update(f"polls/{PUBLIC}", {"redVotes": 100}))


# --- Reports -------------------------------------------------------------------------


def report(code, uid, reports, hidden=False):
    return (
        fs.create(f"polls/{code}/reports/{uid}", {"at": ServerTime()}),
        fs.update(f"polls/{code}", {"reports": reports, "hidden": hidden}),
    )


def test_three_reports_hide_a_public_poll():
    assert fs.commit(BEA, *report(PUBLIC, "bea", 1))
    assert not fs.commit(BEA, *report(PUBLIC, "bea", 2))  # once per user
    assert not fs.commit(CARLOS, *report(PUBLIC, "carlos", 2, hidden=True))  # not yet
    assert fs.commit(CARLOS, *report(PUBLIC, "carlos", 2))
    assert not fs.commit(DANI, *report(PUBLIC, "dani", 3))  # must hide now
    assert fs.commit(DANI, *report(PUBLIC, "dani", 3, hidden=True))


def test_only_others_report_and_only_public_polls():
    assert not fs.commit(ANA, *report(PUBLIC, "ana", 1))
    assert not fs.commit(BEA, *report(PRIVATE, "bea", 1))


# --- Feed and "delete my data" -------------------------------------------------------


def test_feed_query_must_ask_for_public_polls():
    assert fs.query(
        BEA, "polls", [("visibility", "==", "public"), ("hidden", "==", False)]
    )
    assert not fs.query(BEA, "polls", [])  # would include private polls
    assert fs.query(ANA, "polls", [("creatorId", "==", "ana")])  # your own


def test_delete_my_data_blanks_names_only():
    assert fs.commit(BEA, *vote(PRIVATE, "bea", name="Bea"))
    assert fs.query(BEA, "votes", [("voterId", "==", "bea")], all_descendants=True)
    assert fs.commit(BEA, fs.update(f"polls/{PRIVATE}/votes/bea", {"name": ""}))
    assert not fs.commit(BEA, fs.update(f"polls/{PRIVATE}/votes/bea", {"side": "blue"}))
    assert fs.commit(ANA, fs.update(f"polls/{PUBLIC}", {"creatorName": ""}))
    assert not fs.commit(BEA, fs.update(f"polls/{PUBLIC}", {"creatorName": ""}))
