"""Firestore persistence for the non-aggression pact.

One document, `pactos/actual`, holding the manager ids the owner has agreed not
to attack. Like `rebuild_store`, the logic that reads the pact stays pure and
this module is its only route to Firestore.

A single document rather than a collection — the pact is one short list,
rewritten whole on every toggle, and never queried by anything but "give me all
of it".

**Deliberately not keyed by season**, unlike `rebuild_store`. A rebuild plan is
ephemeral and belongs to the deficit that produced it; an agreement with a
rival is a standing one. Season-keyed, the pact would empty itself at every
rollover without a word, and it would fail *open* — the first `/emergencia` of
the new year proposing the friend the pact exists to protect. It changes when
the owner changes it in `/pacto`, and at no other moment.
"""

from core.sdk import firestore as fs
from core.utils import get_logger

logger = get_logger(__name__)

COLLECTION = "pactos"
DOCUMENT = "actual"


def _manager_id(raw) -> int | None:
    """Biwenger manager id from whatever Firestore handed back.

    Ids are ints in Biwenger, but a document written by hand (or by an older
    version of this code) can hold strings. Comparing the two silently never
    matches, which would leave the pact in place and doing nothing — so the
    whole store normalises on the way in. An unparseable entry is dropped,
    never raised: one junk id must not blind the rest of the pact.
    """
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Pact entry is not a manager id.", extra={"entry": repr(raw)})
        return None


def load() -> set[int]:
    """Manager ids under the pact. Empty when no pact was ever saved — that
    is the normal state of a league without one, not an error."""
    document = fs.get_document(COLLECTION, DOCUMENT) or {}
    ids = (_manager_id(raw) for raw in document.get("manager_ids") or [])
    return {manager_id for manager_id in ids if manager_id is not None}


def toggle(manager_id: int) -> bool:
    """Add or remove one manager. Returns True when they ended up protected.

    The boolean is the contract, not a convenience: the bot renders the new
    state from it instead of re-reading, so a toggle is one round trip.
    """
    manager_id = int(manager_id)
    protected = load()
    now_protected = manager_id not in protected
    if now_protected:
        protected.add(manager_id)
    else:
        protected.discard(manager_id)
    fs.set_document(COLLECTION, DOCUMENT, {"manager_ids": sorted(protected)})
    logger.info(
        "Pact toggled.",
        extra={"manager_id": manager_id, "protected": now_protected},
    )
    return now_protected
