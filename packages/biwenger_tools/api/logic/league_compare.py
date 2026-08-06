"""Where every squad stands: team value and projected points, ranked.

Two questions the league argues about all season, not just in August. The draft
post-mortem asks them of the fifteen players each manager drafted; this asks
them of whatever they own today, which after the first clausulazo is not the
same squad at all.

Shared so the two callers differ only in where the squads come from:

- `rank` and `render` take a `{manager: {value, projection, ...}}` map and know
  nothing about drafts, prices or Biwenger.
- `collect` builds that map from the live league — seven squad reads plus the
  competition payload and one Jornada Perfecta fetch.

`gain` is optional on purpose. Right after the draft "what it cost against what
it is worth" is the interesting number; a month later nobody remembers what a
squad cost, because half of it arrived by clause.
"""

import time

from core.sdk.jp import get_predict_rate
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import SCORE_SF

logger = get_logger(__name__)


def _eur(amount) -> str:
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")


def _thousands(number) -> str:
    return f"{number:,}".replace(",", ".")


def collect(ctx) -> dict:
    """`{manager: {value, projection, size}}` for every squad in the league.

    Reuses the caller's context so a report chained onto something else pays
    for no second round-trip.
    """
    managers = ctx.biwenger.get_league_users(config.LEAGUE_DATA_URL)
    out = {}
    for manager_id, name in managers.items():
        squad = ctx.biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        rows = build_squad_rows(squad, ctx.biwenger_players, ctx.jp_index)
        out[name] = {
            "value": sum(r.get("price") or 0 for r in rows),
            "projection": sum(
                get_predict_rate(r.get("jp_player"), SCORE_SF) or 0 for r in rows
            ),
            "size": len(rows),
        }
        logger.info("Squad measured.", extra={"manager": name, "size": len(rows)})
    return out


# A squad read per manager is nine requests against a budget the whole league
# shares, and this hangs off a button. Repeat taps within the window reuse the
# answer instead of re-asking Biwenger the same question.
_CACHE_TTL_SECONDS = 300
_cache: tuple[float, dict] | None = None


def collect_cached(ctx) -> dict:
    """`collect`, but at most once every few minutes."""
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _CACHE_TTL_SECONDS:
        logger.info("League comparison served from cache.")
        return _cache[1]
    summary = collect(ctx)
    _cache = (now, summary)
    return summary


def reset_cache() -> None:
    """Drop the cached comparison. Tests and the local runner call this."""
    global _cache
    _cache = None


def rank(summary: dict, key: str) -> list:
    """Managers ordered by `key`, best first."""
    return sorted(summary, key=lambda m: -summary[m].get(key, 0))


def render(summary: dict, title: str, note: str = "") -> str:
    """The two rankings as one Telegram message.

    Value and projection get equal billing and no combined score: they answer
    different questions, and merging them needs a weighting that would be
    invented rather than measured.
    """
    has_gain = any("gain" in record for record in summary.values())
    value_rows = "\n".join(
        f"{i}. <b>{m}</b> — {_eur(summary[m]['value'])}"
        + (f" ({_eur(summary[m]['gain'])} sobre lo que pagó)" if has_gain else "")
        for i, m in enumerate(rank(summary, "gain" if has_gain else "value"), 1)
    )
    projection_rows = "\n".join(
        f"{i}. <b>{m}</b> — {_thousands(summary[m]['projection'])} SF"
        for i, m in enumerate(rank(summary, "projection"), 1)
    )
    heading = (
        "💰 <b>Quién compró mejor</b>" if has_gain else "💰 <b>Equipo más caro</b>"
    )
    body = (
        f"{title}\n\n"
        f"{heading}\n{value_rows}\n\n"
        f"📈 <b>Quién proyecta más</b>\n{projection_rows}"
    )
    return f"{body}\n\n<i>{note}</i>" if note else body
