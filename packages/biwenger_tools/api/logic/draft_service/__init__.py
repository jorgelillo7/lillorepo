"""Persistence + orchestration for the annual snake draft — `/draft/*`.

Wraps the pure engine in `logic/draft.py` with:

- Firestore persistence of manager registration, the serialised
  `DraftState`, and a per-pick idempotency guard.
- The Biwenger `transfer_player`/`release_player`/`apply_bonus` calls that
  actually move a player and charge or refund a manager.
- Free-text name -> market player resolution for the Telegram pick flow.

Every public function returns a plain dict with a `message` field — a
ready-to-send Spanish string — because the bot layer holds no business
logic of its own.

Firestore layout (collection paths, see `core/sdk/firestore.py`):
    draft/{season}/managers  -- doc id = telegram_user_id (string)
    draft/{season}/picks     -- doc id = "R{round:02d}P{position:02d}"
    draft/{season}/state     -- single doc, id `STATE_DOC_ID`

`DRAFT_APPLY_TO_BIWENGER` gates the Biwenger *writes* only: reading the
cf-base player database to resolve the canonical Biwenger id happens either
way — it is side-effect-free, and the same real ids are needed whether or not
the gate is later flipped on.

Undo is a `release_player` + `apply_bonus` pair rather than `revertOffer`:
Biwenger issues no identifier for an admin transfer (the POST answers 204 with
an empty body and no headers, and the `adminTransfer` board entries carry no
`id`), so there is nothing to revert *by*.

Idempotency: a pick is only ever written through the deterministic
`R{round}P{position}` doc id. `_reserve_pick` creates that doc inside a
Firestore transaction, failing (returning "duplicate") if it already
exists — this is what makes retried Telegram webhooks and duplicate bot
taps safe. The Biwenger transfer call itself happens *after* the
transaction commits, never inside it (a transaction body can be re-run by
Firestore on contention, and Biwenger's transfer endpoint has no
idempotency key of its own).

Split by concern; this module is the surface everything else imports.

    store     Firestore paths, document ids, the shared client
    managers  the `/soy` roll-call and its Telegram bindings
    state     the turn state and the open/closed lifecycle
    market    the frozen CSV joined to Biwenger ids
    picks     reserve, apply, undo — everything that moves a player

The operational scripts in `packages/biwenger_tools/scripts/draft/` are
consumers too, so `load_state`, `lifecycle` and `mention` are public: they were
underscored and called from outside anyway, which is worse than either option.
"""

from .managers import (  # noqa: F401
    _get_registered_manager,
    _resolve_manager_name,
    list_draft_managers,
    register_manager,
)
from .market import (  # noqa: F401
    _fetch_market_rows,
    _load_market,
    _transfer_landed,
    _with_session,
    reset_market_cache,
    reset_session_cache,
)
from .picks import (  # noqa: F401
    _applied_response,
    _apply_confirmed_pick,
    _duplicate_pick_response,
    _eur,
    _finalize_pick,
    _reserve_pick,
    confirm_pick,
    export_picks,
    submit_pick,
    undo_last_pick,
)
from .state import (  # noqa: F401
    _reject_if_closed,
    _save_state,
    close_draft,
    get_state,
    lifecycle,
    load_state,
    mention,
    open_draft,
)
from .store import (  # noqa: F401
    ERROR_BIWENGER_TRANSFER_FAILED,
    ERROR_DRAFT_CLOSED,
    ERROR_NOT_REGISTERED,
    ERROR_PICK_IN_PROGRESS,
    LIFECYCLE_DOC_ID,
    PICK_STATUS_APPLIED,
    PICK_STATUS_RESERVED,
    PICK_STATUS_REVERTED,
    STATE_DOC_ID,
    _format_wait,
    _managers_path,
    _pick_doc_id,
    _picks_path,
    _rejected,
    _state_path,
)
