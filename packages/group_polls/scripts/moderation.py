"""Pure helpers for the moderation CLI: which polls need a look and how to show them."""

import datetime as dt

# Keep in sync with firestore.rules and the app's Limits.REPORTS_TO_HIDE.
REPORTS_TO_HIDE = 3


def needs_review(poll: dict) -> bool:
    """Hidden by reports, or reported at least once."""
    return bool(poll.get("hidden")) or int(poll.get("reports", 0)) > 0


def summary(code: str, poll: dict, now: dt.datetime) -> str:
    """One line per poll: state, reports, votes, age, creator and the question."""
    created = poll.get("createdAt")
    age = f"{(now - created).days} d" if isinstance(created, dt.datetime) else "?"
    state = "🙈 hidden" if poll.get("hidden") else "👀 visible"
    creator = poll.get("creatorName") or "(anonymous)"
    votes = int(poll.get("redVotes", 0)) + int(poll.get("blueVotes", 0))
    return (
        f"{code}  {state}  ⚠️ {int(poll.get('reports', 0))}  🗳 {votes}  {age}  "
        f"{creator} [{poll.get('creatorId', '?')}]  "
        f"{poll.get('visibility', '?')}/{poll.get('language', '?')}\n"
        f"    {poll.get('question', '')}  "
        f"🔴 {poll.get('red', '')} / 🔵 {poll.get('blue', '')}"
    )


def review_queue(polls: dict[str, dict]) -> list[str]:
    """Codes to review, most reported first."""
    return sorted(
        (c for c, p in polls.items() if needs_review(p)),
        key=lambda c: -int(polls[c].get("reports", 0)),
    )
