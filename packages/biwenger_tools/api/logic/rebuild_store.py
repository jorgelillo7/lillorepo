"""Firestore persistence for `/emergencia`'s rebuild plans.

Mirrors `draft_service` for `draft.py`: `rebuild.py` stays pure (planning
only, no I/O); this module owns the one collection the flow needs,
`emergencia/{season}/planes/{plan_id}`, and is `emergency.py`'s only route
to it.
"""

import time
import uuid
from typing import Optional

from core.sdk import firestore as fs
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.rebuild import Plan


def _plans_path(season: str) -> str:
    return f"emergencia/{season}/planes"


def store(plan: Plan) -> str:
    """Persist `plan` thinly and return the new document's id.

    Keeps only what execution needs to re-resolve and re-verify each
    signing later: `bw_id`, `owner_user_id`, `line`, `reserved`,
    `clause_at_plan`. Never `jp_player` — a candidate row carries the whole
    provider payload, and this document is read exactly once, by the
    manager's own confirmation tap. Names are re-resolved at execution from
    the players map, the way `execute_clausulazo` already does for its
    success message.
    """
    plan_id = uuid.uuid4().hex
    doc = {
        "formation": plan.formation,
        "cash_before": plan.cash_before,
        "created_at": time.time(),
        "signings": [
            {
                "bw_id": signing.row["bw_id"],
                "owner_user_id": signing.row["owner_user_id"],
                "line": signing.line,
                "reserved": signing.reserved,
                "clause_at_plan": signing.row["clause_value"],
            }
            for signing in plan.signings
        ],
    }
    fs.set_document(_plans_path(config.CURRENT_SEASON), plan_id, doc)
    return plan_id


def load(plan_id: str) -> Optional[dict]:
    """A non-destructive read of the stored plan, or `None`.

    Does not claim it — a caller about to execute the plan (spend money on
    it) must use `claim` instead, so a duplicate call can never read the
    same still-present document twice.
    """
    return fs.get_document(_plans_path(config.CURRENT_SEASON), plan_id)


def claim(plan_id: str) -> Optional[dict]:
    """Atomically read-and-delete the stored plan, or `None` if there was
    nothing left to claim.

    Mirrors `draft_service.picks._reserve_pick`: the read and the delete
    happen inside one Firestore transaction, so two calls for the same
    `plan_id` — a genuine race, a crash-triggered retry, or simply a fast
    double tap on the confirm button — can only ever have one of them see
    the document. The loser gets `None` before it can place a single
    `place_clausulazo` call.

    Deliberately at-most-once, not resumable: claiming happens once, up
    front, before any signing is executed. A crash partway through the
    loop loses whatever signings had not yet been attempted, and the
    document is already gone — the owner re-runs `/emergencia` rather than
    the same stale basket re-executing against a market that has moved.
    Each retry here spends real money, which is exactly why "at most once"
    beats "resumable" on this path.
    """
    season = config.CURRENT_SEASON

    def txn(transaction):
        client = fs.get_client()
        ref = client.collection(_plans_path(season)).document(plan_id)
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return None
        transaction.delete(ref)
        return snapshot.to_dict()

    return fs.run_transaction(txn)
