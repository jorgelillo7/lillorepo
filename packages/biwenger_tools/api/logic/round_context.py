"""Where the season is, from Biwenger rather than inferred.

Pure functions: the caller fetches `BiwengerClient.get_round()` and hands the
payload in.

Two questions the lineup messages could not answer:

- **Is this matchday still open?** The reglamento's *jornada única* (2.5.8)
  says a round is not final until every match is played, and the platform has
  been inferring that from Jornada Perfecta. Biwenger states it: the round
  carries a `status` and every game its own.
- **When does the next one start?** Which matters twice — cash has to be
  positive before it, and clauses freeze 24 h before its first kickoff.

**The next round is not the next number.** 2026/27 interleaves postponed
rounds: with Jornada 3 active, the next to be played is Jornada 6 and Jornada
4 follows it. Biwenger's own `next` is the only reliable answer — the round
number lies and `season.rounds[]` is not in chronological order.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.constants import MADRID_TZ

# Biwenger freezes clauses this long before a matchday's first kickoff.
# Owner-stated from the platform's behaviour, not read from the API — see
# `openspec/project.md`, "The rules the platform runs inside".
CLAUSE_FREEZE_BEFORE = timedelta(hours=24)

_PLAYED = "finished"


@dataclass(frozen=True)
class RoundContext:
    """`None` on every field is a legitimate answer: the read is best-effort
    and a message with no context beats no message."""

    name: str | None = None
    is_open: bool = False
    played: int = 0
    total: int = 0
    next_name: str | None = None
    next_kickoff: datetime | None = None

    @property
    def clause_deadline(self) -> datetime | None:
        """When clauses freeze for the next round, or `None` if unknown."""
        if self.next_kickoff is None:
            return None
        return self.next_kickoff - CLAUSE_FREEZE_BEFORE


def _kickoff(game: dict) -> datetime | None:
    stamp = game.get("date")
    if not isinstance(stamp, (int, float)):
        return None
    return datetime.fromtimestamp(stamp, MADRID_TZ)


def read(round_data: dict | None) -> RoundContext:
    """A `RoundContext` from `get_round()`'s payload. Never raises.

    An unreadable or partial payload yields an empty context rather than an
    exception: this decorates a message, and losing the lineup because the
    calendar could not be read would be the wrong trade.
    """
    if not isinstance(round_data, dict):
        return RoundContext()

    games = [g for g in (round_data.get("games") or []) if isinstance(g, dict)]
    played = sum(1 for g in games if g.get("status") == _PLAYED)

    nxt = round_data.get("next") or {}
    kickoffs = [
        k
        for k in (_kickoff(g) for g in (nxt.get("games") or []) if isinstance(g, dict))
        if k is not None
    ]

    return RoundContext(
        name=round_data.get("name"),
        # A round is open while it has an unplayed match in it — which is the
        # reglamento's rule, said by the source instead of guessed.
        is_open=played < len(games) if games else False,
        played=played,
        total=len(games),
        next_name=nxt.get("name"),
        next_kickoff=min(kickoffs) if kickoffs else None,
    )


def format_line(context: RoundContext) -> str:
    """One line for the lineup messages, or `""` when nothing is known."""
    if not context.name:
        return ""

    state = "en juego" if context.is_open else "cerrada"
    line = f"📅 {context.name} — {context.played}/{context.total} jugados, {state}"

    if context.next_name and context.next_kickoff:
        kickoff = context.next_kickoff.strftime("%a %d/%m %H:%M")
        line += f"\n   Siguiente: {context.next_name}, primer partido {kickoff}"
        deadline = context.clause_deadline
        if deadline is not None:
            line += (
                f"\n   🔒 Cláusulas se congelan el "
                f"{deadline.strftime('%a %d/%m %H:%M')} — hasta entonces "
                "puedes clausular y te pueden clausular"
            )
    return line
