"""Whether now is the moment to set the lineup: half an hour before the first
kick-off of the round the lineup lands on.

Biwenger freezes the whole eleven at a matchday's first kick-off
(`settings.lineupRoundChanges = 0`, `docs/technical/backend/
biwenger-official-rules.md`), so that kick-off is the only deadline a lineup
has. A tick every `TICK` asks; exactly one tick per round falls in the window.
Pure.
"""

from datetime import datetime, timedelta

from packages.biwenger_tools.api.logic import round_context
from packages.biwenger_tools.api.logic.projection_ledger import target_round

LEAD = timedelta(minutes=30)
TICK = timedelta(minutes=15)


def due(round_data: dict, now: datetime) -> int | None:
    """The round id to set the lineup for if its first kick-off is within
    (`LEAD` − `TICK`, `LEAD`] of `now`, else `None`.

    The round is `target_round`'s: the current one before it starts, the next
    once it is under way. A postponed round ("Jornada 6 (aplazada)") lists
    every game of its matchday, so its first kick-off is long past and it is
    never the target.
    """
    round_id = target_round(round_data, now)
    if round_id is None:
        return None
    games = (
        round_data.get("games")
        if round_id == round_data.get("id")
        else (round_data.get("next") or {}).get("games")
    )
    kickoff = round_context.first_kickoff(games)
    if kickoff is None:
        return None
    return round_id if LEAD - TICK < kickoff - now <= LEAD else None
