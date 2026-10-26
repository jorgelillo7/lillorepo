"""One digest, one read of each thing Biwenger cannot change under it.

The daily digest chains steps that each read the calendar, the squad and the
market for themselves, which spent some fifteen requests a morning of an
account window shared with the phone app. `ReadOnce` wraps the session for
the length of one digest and answers those repeats from what it already read.

Only three reads are kept. Everything else — pending bids, received offers,
cash, the saved lineup — is read again after a write in the same digest, and
passes straight through. A failed or empty read is never kept, so a step that
follows a failure gets its own try.
"""

from typing import Any, Callable

# Writes after which the squad is still the squad: a lineup, a bid that has
# not been resolved, a listing. Any other write — an accepted offer, a clause,
# an admin operation — may have moved a player, and the squad is read again.
_KEEPS_SQUAD = frozenset(
    {"set_lineup", "place_market_bid", "list_squad_for_sale", "withdraw_all_sales"}
)
# The market changes with anything but a lineup: a listing adds the squad to it.
_KEEPS_MARKET = frozenset({"set_lineup"})


class ReadOnce:
    """A Biwenger session that reads each round, the squad and the market at
    most once, until a write that could change them."""

    def __init__(self, biwenger: Any) -> None:
        self._biwenger = biwenger
        self._rounds: dict = {}
        self._squads: dict = {}
        self._market: dict = {}

    def get_round(self, round_id: int | None = None) -> dict:
        return _kept(self._rounds, round_id, lambda: self._biwenger.get_round(round_id))

    def get_manager_squad(self, url_template: str, manager_id) -> list:
        return _kept(
            self._squads,
            (url_template, manager_id),
            lambda: self._biwenger.get_manager_squad(url_template, manager_id),
        )

    def get_market_players(self, market_url: str) -> list:
        return _kept(
            self._market,
            market_url,
            lambda: self._biwenger.get_market_players(market_url),
        )

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._biwenger, name)
        if not callable(attr) or name.startswith("get_"):
            return attr

        def write(*args, **kwargs):
            try:
                return attr(*args, **kwargs)
            finally:
                # A write that raised may have landed all the same.
                if name not in _KEEPS_SQUAD:
                    self._squads.clear()
                if name not in _KEEPS_MARKET:
                    self._market.clear()

        return write


def _kept(store: dict, key, read: Callable[[], Any]) -> Any:
    if key in store:
        return store[key]
    value = read()
    if value:
        store[key] = value
    return value
