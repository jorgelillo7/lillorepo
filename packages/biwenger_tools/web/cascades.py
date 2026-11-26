"""Clausulazo cascades: the days most of a season's league claused each other.

Pure. Spec: `openspec/specs/biwenger_tools/web-dataviz/spec.md`, "Clausulazo
cascades get a table of their own on /mercado".
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from core.domain.models import Clausulazo

# A cascade day runs from 06:00 to 05:59 the next morning: the nights run late,
# and a midnight cut split 16/02/26 in two.
DAY_STARTS = timedelta(hours=6)
MIN_CLAUSULAZOS = 5
# Teams of the season that may stay out of a cascade.
MAX_UNINVOLVED = 2

_FECHA = "%d-%m-%Y %H:%M"


@dataclass(frozen=True)
class Cascade:
    """One cascade day. `baile` is its clausulazos oldest first; `starters` the
    first one, or every one of its first minute when they were stored without
    their board second and place, which alone order a minute."""

    day: date
    first: str
    last: str
    baile: tuple[Clausulazo, ...]
    starters: tuple[Clausulazo, ...]
    involved: int
    active: int
    responses: int
    total: int
    top_payer: str
    top_paid: int
    top_paid_count: int
    most_hit: str
    hits: int

    @property
    def count(self) -> int:
        return len(self.baile)


def _time(c: Clausulazo) -> datetime:
    return datetime.strptime(c.fecha, _FECHA)


def _placed(c: Clausulazo) -> bool:
    """Whether it was stored with its board second and place."""
    return c.segundos is not None and c.orden is not None


def _key(c: Clausulazo) -> tuple:
    return (_time(c), c.segundos or 0, c.orden or 0)


def _before(other: Clausulazo, c: Clausulazo) -> bool:
    """`other` came before `c`: by board second and place when both carry them,
    else by the minute, where a tie counts as before."""
    if _placed(other) and _placed(c):
        return _key(other) < _key(c)
    return _time(other) <= _time(c)


def _teams(clausulazos: list[Clausulazo]) -> set[str]:
    return {c.equipo_comprador for c in clausulazos} | {
        c.equipo_vendedor for c in clausulazos
    }


def find_cascades(clausulazos: list[Clausulazo]) -> list[Cascade]:
    """The cascades in one season's clausulazos, newest first; cancelled ones
    count for nothing."""
    valid = sorted((c for c in clausulazos if not c.anulado), key=_key)
    active = len(_teams(valid))
    days: dict[date, list[Clausulazo]] = {}
    for c in valid:
        days.setdefault((_time(c) - DAY_STARTS).date(), []).append(c)
    cascades = [
        _cascade(day, baile, active)
        for day, baile in days.items()
        if len(baile) >= MIN_CLAUSULAZOS
        and len(_teams(baile)) >= active - MAX_UNINVOLVED
    ]
    return sorted(cascades, key=lambda c: c.day, reverse=True)


def _cascade(day: date, baile: list[Clausulazo], active: int) -> Cascade:
    times = [_time(c) for c in baile]
    responses = sum(
        1
        for c in baile
        if any(
            other is not c
            and other.equipo_vendedor == c.equipo_comprador
            and _before(other, c)
            for other in baile
        )
    )
    first_minute = [c for c, t in zip(baile, times) if t == times[0]]
    starters = first_minute[:1] if all(map(_placed, first_minute)) else first_minute
    paid: Counter[str] = Counter()
    bought: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    lost: Counter[str] = Counter()
    for c in baile:
        paid[c.equipo_comprador] += c.precio
        bought[c.equipo_comprador] += 1
        hits[c.equipo_vendedor] += 1
        lost[c.equipo_vendedor] += c.precio
    top_payer = max(paid, key=lambda team: (paid[team], bought[team]))
    most_hit = max(hits, key=lambda team: (hits[team], lost[team]))
    return Cascade(
        day=day,
        first=times[0].strftime("%H:%M"),
        last=times[-1].strftime("%H:%M"),
        baile=tuple(baile),
        starters=tuple(starters),
        involved=len(_teams(baile)),
        active=active,
        responses=responses,
        total=sum(paid.values()),
        top_payer=top_payer,
        top_paid=paid[top_payer],
        top_paid_count=bought[top_payer],
        most_hit=most_hit,
        hits=hits[most_hit],
    )
