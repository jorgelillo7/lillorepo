"""Tests for `api/logic/draft_service.py` — persistence, idempotency and
the Biwenger write gate.

Firestore is faked with a tiny in-memory stand-in (`FakeFirestore`) swapped
in for `draft_service.fs`: real enough to exercise `run_transaction` +
deterministic doc ids, without touching the emulator. Biwenger is a
`MagicMock` swapped in for `draft_service.build_biwenger_session`.

The pure engine (`logic/draft.py`) is tested elsewhere (`test_draft.py`);
these tests only cover what this module adds on top of it.
"""

from unittest.mock import MagicMock

import pytest

from core.constants import LEAGUE_MEMBERS
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft, draft_service

RUBEN_ID = 7727371  # first to pick, per draft.DEFAULT_ORDER
JAVI_ID = 7728598  # second to pick
JORGE_ID = 1372802

TG_RUBEN = "111"
TG_JAVI = "222"
TG_JORGE = "333"
TG_ADMIN = "999"

MESSI_ID = 101
RONALDO_ID = 102
MODRIC_ID = 103


# ---------------------------------------------------------------------------
# Fake Firestore — in-memory, keyed exactly like `core/sdk/firestore.py`
# ---------------------------------------------------------------------------


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, coll, doc_id):
        self._coll = coll
        self._doc_id = doc_id

    def get(self, transaction=None):
        return _FakeSnapshot(self._coll.get(self._doc_id))


class _FakeCollRef:
    def __init__(self, root, path):
        self._store = root.setdefault(path, {})

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeTransaction:
    def set(self, ref, data):
        ref._coll[ref._doc_id] = dict(data)

    def update(self, ref, data):
        current = dict(ref._coll.get(ref._doc_id) or {})
        current.update(data)
        ref._coll[ref._doc_id] = current


class FakeFirestore:
    """Stand-in for `core.sdk.firestore`, swapped onto `draft_service.fs`."""

    def __init__(self):
        self.root: dict[str, dict] = {}

    def get_client(self):
        return self

    def collection(self, path):
        return _FakeCollRef(self.root, path)

    def run_transaction(self, fn):
        return fn(_FakeTransaction())

    def get_document(self, collection_path, doc_id):
        return self.root.get(collection_path, {}).get(doc_id)

    def list_documents(self, collection_path):
        return list(self.root.get(collection_path, {}).items())

    def set_document(self, collection_path, doc_id, data, merge=False):
        coll = self.root.setdefault(collection_path, {})
        if merge and doc_id in coll:
            coll[doc_id] = {**coll[doc_id], **data}
        else:
            coll[doc_id] = dict(data)

    def query(
        self,
        collection_path,
        field=None,
        op="==",
        value=None,
        order_by=None,
        direction="ASCENDING",
        limit=None,
    ):
        docs = list(self.root.get(collection_path, {}).values())
        if field is not None:
            docs = [d for d in docs if d.get(field) == value]
        if order_by is not None:
            docs = sorted(
                docs, key=lambda d: d.get(order_by), reverse=(direction == "DESCENDING")
            )
        if limit is not None:
            docs = docs[:limit]
        return docs


# ---------------------------------------------------------------------------
# Frozen-market fixture: 3 named players + ample cheap filler at every
# position, so budget/composition checks in `validate_pick` never get in
# the way of the scenarios these tests care about.
# ---------------------------------------------------------------------------


def _biwenger_players_map():
    players = {
        MESSI_ID: {"id": MESSI_ID, "name": "Lionel Messi"},
        RONALDO_ID: {"id": RONALDO_ID, "name": "Cristiano Ronaldo"},
        MODRIC_ID: {"id": MODRIC_ID, "name": "Luka Modric"},
    }
    next_id = 200
    for i in range(20):
        for prefix in ("GK", "DEF", "MID", "FWD"):
            players[next_id] = {"id": next_id, "name": f"Filler {prefix} {i}"}
            next_id += 1
    return players


def _write_market_csv(path):
    lines = ["Equipo;Jugador;Posición;Puntos;Precio"]
    lines.append("Barcelona;Lionel Messi;Delantero;500;5000000")
    lines.append("Real Madrid;Cristiano Ronaldo;Delantero;480;6000000")
    lines.append("Real Madrid;Luka Modric;Centrocampista;300;200000")
    for i in range(20):
        lines.append(f"Team{i};Filler GK {i};Portero;10;0")
        lines.append(f"Team{i};Filler DEF {i};Defensa;10;0")
        lines.append(f"Team{i};Filler MID {i};Centrocampista;10;0")
        lines.append(f"Team{i};Filler FWD {i};Delantero;10;0")
    path.write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _draft_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRAFT_SEASON", "test-season")
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", False)
    monkeypatch.setattr(config, "DRAFT_ADMIN_TELEGRAM_ID", TG_ADMIN)
    csv_path = tmp_path / "market.csv"
    _write_market_csv(csv_path)
    monkeypatch.setattr(config, "DRAFT_MARKET_CSV_PATH", str(csv_path))
    draft_service.reset_market_cache()


@pytest.fixture
def fake_fs(monkeypatch):
    fake = FakeFirestore()
    monkeypatch.setattr(draft_service, "fs", fake)
    return fake


@pytest.fixture
def biwenger(monkeypatch):
    mock = MagicMock()
    mock.get_all_players_data_map.return_value = _biwenger_players_map()
    mock.get_all_teams_map.return_value = {}
    monkeypatch.setattr(draft_service, "build_biwenger_session", lambda: mock)
    return mock


def _players_by_id(biwenger_mock):
    return draft_service._load_market(biwenger_mock)


# ---------------------------------------------------------------------------
# Manager registration
# ---------------------------------------------------------------------------


def test_register_manager_resolves_exact_name(fake_fs):
    result = draft_service.register_manager(TG_RUBEN, "Ruben")
    assert result == {
        "ok": True,
        "manager_id": RUBEN_ID,
        "manager_name": "Ruben",
        "message": result["message"],
    }
    assert "Ruben" in result["message"]
    stored = fake_fs.get_document(draft_service._managers_path("test-season"), TG_RUBEN)
    assert stored == {
        "telegram_user_id": TG_RUBEN,
        "manager_id": RUBEN_ID,
        "manager_name": "Ruben",
    }


def test_register_manager_resolves_unambiguous_prefix(fake_fs):
    result = draft_service.register_manager(TG_JAVI, "jav")
    assert result["ok"] is True
    assert result["manager_id"] == JAVI_ID


def test_register_manager_rejects_unknown_name(fake_fs):
    result = draft_service.register_manager(TG_RUBEN, "Zzzz")
    assert result["ok"] is False
    assert result["manager_id"] is None
    assert "Zzzz" in result["message"]


def test_register_manager_rejects_spectator_not_in_draft_order(fake_fs):
    """Alberto (the cronista) is a `LEAGUE_MEMBERS` entry but not a draft
    manager — registering as him must fail."""
    assert "Alberto" not in [LEAGUE_MEMBERS[m] for m in draft.DEFAULT_ORDER]
    result = draft_service.register_manager(TG_RUBEN, "Alberto")
    assert result["ok"] is False


def test_register_manager_overwrite_is_idempotent(fake_fs):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.register_manager(TG_RUBEN, "Javi")
    stored = fake_fs.get_document(draft_service._managers_path("test-season"), TG_RUBEN)
    assert stored["manager_id"] == JAVI_ID


# ---------------------------------------------------------------------------
# GET /draft/state
# ---------------------------------------------------------------------------


def test_get_state_fresh_draft(fake_fs):
    state = draft_service.get_state()
    assert state["completed"] is False
    assert state["pick_number"] == 1
    assert state["round"] == 1
    assert state["position"] == 1
    assert state["manager_id"] == RUBEN_ID
    assert state["manager_name"] == "Ruben"
    assert state["budgets"]["Ruben"] == 50_000_000
    assert state["spent"]["Ruben"] == 0
    assert state["squad_counts"]["Ruben"] == 0
    assert "Ruben" in state["message"]


def test_get_state_advances_turn_after_a_pick(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")
    state = draft_service.get_state()
    assert state["manager_id"] == JAVI_ID
    assert state["squad_counts"]["Ruben"] == 1
    assert state["spent"]["Ruben"] == 5_000_000


# ---------------------------------------------------------------------------
# POST /draft/pick (+ /confirm)
# ---------------------------------------------------------------------------


def test_submit_pick_rejects_unregistered_user(fake_fs, biwenger):
    result = draft_service.submit_pick("999999", "messi")
    assert result["status"] == "rejected"
    assert result["error"] == draft_service.ERROR_NOT_REGISTERED
    biwenger.transfer_player.assert_not_called()


def test_submit_pick_rejects_unknown_player(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.submit_pick(TG_RUBEN, "xyzxyzxyz nobody")
    assert result["status"] == "rejected"
    assert result["error"] == draft.DraftError.PLAYER_UNKNOWN.name


def test_submit_pick_ambiguous_query_returns_candidates(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.submit_pick(TG_RUBEN, "filler gk")
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) > 1
    assert all("player_id" in c and "name" in c for c in result["candidates"])


def test_submit_pick_rejects_out_of_turn(fake_fs, biwenger):
    draft_service.register_manager(TG_JAVI, "Javi")
    result = draft_service.submit_pick(TG_JAVI, "messi")
    assert result["status"] == "rejected"
    assert result["error"] == draft.DraftError.NOT_YOUR_TURN.name
    biwenger.transfer_player.assert_not_called()


def test_submit_pick_applies_with_gate_off(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.submit_pick(TG_RUBEN, "messi")
    assert result["status"] == "applied"
    assert result["player"]["player_id"] == MESSI_ID
    assert result["remaining"] == 50_000_000 - 5_000_000
    assert result["next_manager"] == "Javi"
    assert "simulación" in result["message"]


def test_confirm_pick_applies_explicit_player_id(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.confirm_pick(TG_RUBEN, MODRIC_ID)
    assert result["status"] == "applied"
    assert result["player"]["player_id"] == MODRIC_ID
    assert result["remaining"] == 50_000_000 - 200_000


# ---------------------------------------------------------------------------
# The Biwenger write gate
# ---------------------------------------------------------------------------


def test_gate_off_never_calls_biwenger_transfer_or_board(fake_fs, biwenger):
    """`DRAFT_APPLY_TO_BIWENGER=False` (the default): validation, state and
    Firestore all run, but no Biwenger write happens."""
    assert config.DRAFT_APPLY_TO_BIWENGER is False
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.submit_pick(TG_RUBEN, "messi")

    assert result["status"] == "applied"
    biwenger.transfer_player.assert_not_called()
    biwenger.revert_transfer.assert_not_called()
    biwenger.get_all_clausulazos.assert_not_called()

    state = draft_service._load_state()
    assert MESSI_ID in state.squads[RUBEN_ID]

    pick_doc = fake_fs.get_document(draft_service._picks_path("test-season"), "R01P01")
    assert pick_doc["status"] == draft_service.PICK_STATUS_APPLIED
    assert pick_doc["applied_to_biwenger"] is False


def test_gate_on_calls_biwenger_transfer(fake_fs, biwenger, monkeypatch):
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.submit_pick(TG_RUBEN, "messi")

    assert result["status"] == "applied"
    biwenger.transfer_player.assert_called_once_with(
        player_id=MESSI_ID, manager_id=RUBEN_ID, amount=5_000_000
    )
    pick_doc = fake_fs.get_document(draft_service._picks_path("test-season"), "R01P01")
    assert pick_doc["applied_to_biwenger"] is True
    assert "offer_id" not in pick_doc, "Biwenger issues no id for an admin transfer"


def test_gate_on_biwenger_failure_keeps_pick_reserved_and_rejects(
    fake_fs, biwenger, monkeypatch
):
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    biwenger.transfer_player.side_effect = RuntimeError("Biwenger 500")
    draft_service.register_manager(TG_RUBEN, "Ruben")

    result = draft_service.submit_pick(TG_RUBEN, "messi")
    assert result["status"] == "rejected"
    assert result["error"] == draft_service.ERROR_BIWENGER_TRANSFER_FAILED

    pick_doc = fake_fs.get_document(draft_service._picks_path("test-season"), "R01P01")
    assert pick_doc["status"] == draft_service.PICK_STATUS_RESERVED
    state = draft_service._load_state()
    assert state.squads[RUBEN_ID] == []  # never finalised


# ---------------------------------------------------------------------------
# Idempotency: duplicate pick requests never re-call Biwenger.
# ---------------------------------------------------------------------------


def test_duplicate_applied_pick_does_not_recall_biwenger(
    fake_fs, biwenger, monkeypatch
):
    """The pick doc already exists with status=applied (e.g. the original
    request's response was lost after Biwenger already processed it). A
    retry must echo the previous outcome, never call Biwenger again."""
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    fake_fs.set_document(
        draft_service._picks_path("test-season"),
        "R01P01",
        {
            "round": 1,
            "position": 1,
            "global_pick": 1,
            "manager_id": RUBEN_ID,
            "manager_name": "Ruben",
            "player_id": MESSI_ID,
            "player_name": "Lionel Messi",
            "player_team": "Barcelona",
            "price": 5_000_000,
            "status": draft_service.PICK_STATUS_APPLIED,
            "offer_id": 4242,
            "applied_to_biwenger": True,
        },
    )
    players_by_id = _players_by_id(biwenger)

    result = draft_service._apply_confirmed_pick(
        RUBEN_ID, MESSI_ID, players_by_id, biwenger
    )

    assert result["status"] == "applied"
    assert "ya se aplicó" in result["message"]
    biwenger.transfer_player.assert_not_called()


def test_duplicate_reserved_pick_rejects_without_calling_biwenger(
    fake_fs, biwenger, monkeypatch
):
    """A previous attempt crashed after reserving the slot but before
    Biwenger confirmed — status stays "reserved". A retry must NOT assume
    it's safe to call Biwenger (it might already have gone through)."""
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    fake_fs.set_document(
        draft_service._picks_path("test-season"),
        "R01P01",
        {
            "round": 1,
            "position": 1,
            "global_pick": 1,
            "manager_id": RUBEN_ID,
            "manager_name": "Ruben",
            "player_id": MESSI_ID,
            "player_name": "Lionel Messi",
            "player_team": "Barcelona",
            "price": 5_000_000,
            "status": draft_service.PICK_STATUS_RESERVED,
            "offer_id": None,
            "applied_to_biwenger": False,
        },
    )
    players_by_id = _players_by_id(biwenger)

    result = draft_service._apply_confirmed_pick(
        RUBEN_ID, MESSI_ID, players_by_id, biwenger
    )

    assert result["status"] == "rejected"
    assert result["error"] == draft_service.ERROR_PICK_IN_PROGRESS
    biwenger.transfer_player.assert_not_called()


def test_retried_submit_pick_after_reserve_before_finalize_skips_biwenger(
    fake_fs, biwenger, monkeypatch
):
    """End-to-end reproduction of a lost-response retry: the first call
    reserves the slot and (successfully) calls Biwenger, but crashes before
    `_finalize_pick` runs — so `state` never advances. The retry must see
    the duplicate and must not call `transfer_player` a second time."""
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    draft_service.register_manager(TG_RUBEN, "Ruben")

    def _finalize_without_persisting(manager_id, player_id, players_by_id):
        # Compute the resulting state in memory (for the response) without
        # writing it to Firestore — simulates a crash right after the
        # Biwenger call succeeds but before `_finalize_pick`'s write lands.
        state = draft_service._load_state()
        new_state, _ = draft.apply_pick(state, manager_id, player_id, players_by_id)
        return new_state

    real_finalize = draft_service._finalize_pick
    monkeypatch.setattr(draft_service, "_finalize_pick", _finalize_without_persisting)
    first = draft_service.submit_pick(TG_RUBEN, "messi")
    assert first["status"] == "applied"
    assert biwenger.transfer_player.call_count == 1

    # State was never advanced (finalize was stubbed out) — the retry reads
    # the same fresh state and lands on the same deterministic pick slot.
    monkeypatch.setattr(draft_service, "_finalize_pick", real_finalize)
    second = draft_service.submit_pick(TG_RUBEN, "messi")

    assert biwenger.transfer_player.call_count == 1  # not called again
    assert second["status"] == "applied"


def test_reserve_pick_rejects_second_reservation_of_same_slot(fake_fs, biwenger):
    """Direct unit test of the guard itself: two reservation attempts for
    the same (unadvanced) state collide on the deterministic doc id."""
    players_by_id = _players_by_id(biwenger)
    first = draft_service._reserve_pick(RUBEN_ID, MESSI_ID, players_by_id)
    assert first["outcome"] == "reserved"

    second = draft_service._reserve_pick(RUBEN_ID, MESSI_ID, players_by_id)
    assert second["outcome"] == "duplicate"
    assert second["pick"]["status"] == draft_service.PICK_STATUS_RESERVED


# ---------------------------------------------------------------------------
# POST /draft/undo
# ---------------------------------------------------------------------------


def test_undo_rejects_non_admin(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")
    result = draft_service.undo_last_pick(TG_RUBEN)
    assert result["status"] == "rejected"


def test_undo_rejects_when_no_picks(fake_fs):
    result = draft_service.undo_last_pick(TG_ADMIN)
    assert result["status"] == "rejected"


def test_undo_reverts_last_pick_gate_off(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")

    result = draft_service.undo_last_pick(TG_ADMIN)
    assert result["status"] == "reverted"
    biwenger.revert_transfer.assert_not_called()

    state = draft_service._load_state()
    assert state.squads[RUBEN_ID] == []
    assert state.spent[RUBEN_ID] == 0
    assert draft.whose_turn(state) == RUBEN_ID

    pick_doc = fake_fs.get_document(draft_service._picks_path("test-season"), "R01P01")
    assert pick_doc["status"] == draft_service.PICK_STATUS_REVERTED


def test_undo_releases_the_player_and_refunds_the_price(fake_fs, biwenger, monkeypatch):
    """Undo is a release plus a bonus, never `revertOffer`: Biwenger exposes no
    id for an admin transfer, so there is nothing to revert *by*."""
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")

    result = draft_service.undo_last_pick(TG_ADMIN)
    assert result["status"] == "reverted"
    biwenger.release_player.assert_called_once_with(player_id=MESSI_ID)
    biwenger.revert_transfer.assert_not_called()

    amounts = biwenger.apply_bonus.call_args.kwargs["amounts"]
    assert amounts[RUBEN_ID] == 5_000_000, "the buyer gets his money back"
    assert all(v == 0 for k, v in amounts.items() if k != RUBEN_ID)


def test_undo_works_without_an_offer_id(fake_fs, biwenger, monkeypatch):
    """The board carries no id for admin transfers, so every real pick has
    `offer_id: None` — undo must not depend on it."""
    monkeypatch.setattr(config, "DRAFT_APPLY_TO_BIWENGER", True)
    biwenger.get_all_clausulazos.return_value = {"data": []}
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")

    assert draft_service.undo_last_pick(TG_ADMIN)["status"] == "reverted"
    biwenger.release_player.assert_called_once()


# ---------------------------------------------------------------------------
# GET /draft/export
# ---------------------------------------------------------------------------


def test_export_picks_empty(fake_fs):
    result = draft_service.export_picks()
    assert result["picks"] == []
    assert "no hay" in result["message"].lower()


def test_export_picks_lists_applied_only(fake_fs, biwenger):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.register_manager(TG_JAVI, "Javi")
    draft_service.submit_pick(TG_RUBEN, "messi")

    # A stray reserved-but-never-applied doc must not leak into the export.
    fake_fs.set_document(
        draft_service._picks_path("test-season"),
        "R01P02",
        {
            "round": 1,
            "position": 2,
            "global_pick": 2,
            "manager_id": JAVI_ID,
            "manager_name": "Javi",
            "player_id": RONALDO_ID,
            "player_name": "Cristiano Ronaldo",
            "player_team": "Real Madrid",
            "price": 6_000_000,
            "status": draft_service.PICK_STATUS_RESERVED,
            "offer_id": None,
            "applied_to_biwenger": False,
        },
    )

    result = draft_service.export_picks()
    assert len(result["picks"]) == 1
    assert result["picks"][0]["player_name"] == "Lionel Messi"
    assert result["picks"][0]["manager_name"] == "Ruben"


def test_chained_undos_rewind_the_turn_one_pick_at_a_time(fake_fs, biwenger):
    """Three picks, then three undos: the turn walks back 4 -> 3 -> 2 -> 1 and
    every budget is restored, so a bad run can be unwound to any earlier point."""
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.register_manager(TG_JAVI, "Javi")
    draft_service.register_manager(TG_JORGE, "Jorge")

    for tg, query in ((TG_RUBEN, "messi"), (TG_JAVI, "ronaldo"), (TG_JORGE, "modric")):
        assert draft_service.submit_pick(tg, query)["status"] == "applied"

    assert draft_service.get_state()["pick_number"] == 4

    for expected_pick in (3, 2, 1):
        assert draft_service.undo_last_pick(TG_ADMIN)["status"] == "reverted"
        assert draft_service.get_state()["pick_number"] == expected_pick

    state = draft_service.get_state()
    assert not any(state["spent"].values()), "every euro handed back"
    assert not any(state["squad_counts"].values()), "every squad empty again"
    assert draft_service.undo_last_pick(TG_ADMIN)["status"] == "rejected"


def test_undo_then_repick_reuses_the_same_slot(fake_fs, biwenger):
    """Undo rewinds the turn to the same manager, who re-picks into the same
    deterministic doc id. The idempotency guard must not read that as a
    duplicate, or the draft stalls on the very next pick."""
    draft_service.register_manager(TG_RUBEN, "Ruben")
    first = draft_service.submit_pick(TG_RUBEN, "messi")
    assert first["status"] == "applied"

    undone = draft_service.undo_last_pick(TG_ADMIN)
    assert undone["status"] == "reverted"

    again = draft_service.submit_pick(TG_RUBEN, "ronaldo")
    assert again["status"] == "applied", again
    assert draft_service.get_state()["pick_number"] == 2


def test_export_picks_renders_one_message_per_manager(fake_fs, biwenger):
    """The listing is what makes /exportar useful — a bare count is not."""
    draft_service.register_manager(TG_RUBEN, "Ruben")
    draft_service.submit_pick(TG_RUBEN, "messi")

    result = draft_service.export_picks()
    assert len(result["messages"]) == 1, "one block per manager with picks"
    block = result["messages"][0]
    assert "Ruben" in block
    assert "Lionel Messi" in block
    assert "M" in block, "prices rendered in millions"


def test_export_picks_with_nothing_yet_sends_no_blocks(fake_fs, biwenger):
    result = draft_service.export_picks()
    assert result["messages"] == []
    assert "Todavía no hay fichajes" in result["message"]


def test_picker_tap_never_reassigns_a_registered_user(fake_fs):
    """Picker buttons stay tappable in the chat and are not user-bound; a
    stray tap must not silently rewrite an existing binding."""
    draft_service.register_manager(TG_RUBEN, "Ruben")

    result = draft_service.register_manager(TG_RUBEN, manager_id=JAVI_ID)
    assert result["ok"] is False
    assert "Ruben" in result["message"]
    stored = fake_fs.get_document(draft_service._managers_path("test-season"), TG_RUBEN)
    assert stored["manager_id"] == RUBEN_ID, "binding untouched"


def test_picker_tap_on_own_name_is_a_noop_success(fake_fs):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.register_manager(TG_RUBEN, manager_id=RUBEN_ID)
    assert result["ok"] is True


def test_typed_soy_still_reassigns_explicitly(fake_fs):
    draft_service.register_manager(TG_RUBEN, "Ruben")
    result = draft_service.register_manager(TG_RUBEN, "Javi")
    assert result["ok"] is True
    stored = fake_fs.get_document(draft_service._managers_path("test-season"), TG_RUBEN)
    assert stored["manager_id"] == JAVI_ID
