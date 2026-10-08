"""What the moderation CLI shows and in which order."""

import datetime as dt

from packages.group_polls.scripts.moderation import needs_review, review_queue, summary

NOW = dt.datetime(2026, 10, 7, tzinfo=dt.UTC)


def poll(**overrides):
    base = {
        "visibility": "public",
        "language": "es",
        "question": "¿Playa o montaña?",
        "red": "Playa",
        "blue": "Montaña",
        "creatorId": "u1",
        "creatorName": "Ana",
        "createdAt": NOW - dt.timedelta(days=2),
        "redVotes": 3,
        "blueVotes": 1,
        "reports": 0,
        "hidden": False,
    }
    return base | overrides


def test_reported_or_hidden_polls_need_review():
    assert not needs_review(poll())
    assert needs_review(poll(reports=1))
    assert needs_review(poll(hidden=True))


def test_queue_puts_the_most_reported_first():
    polls = {"a": poll(reports=1), "b": poll(), "c": poll(reports=3, hidden=True)}
    assert review_queue(polls) == ["c", "a"]


def test_summary_shows_state_votes_age_and_creator():
    line = summary("abc", poll(reports=3, hidden=True, creatorName=""), NOW)
    assert "🙈 hidden" in line
    assert "⚠️ 3" in line
    assert "🗳 4" in line
    assert "2 d" in line
    assert "(anonymous)" in line
    assert "¿Playa o montaña?" in line
