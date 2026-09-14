"""Unit tests for the non-aggression pact: `pact_store` + the pure helpers
in `clausulazo_candidates` that tag and drop a pacted manager's players.

The pact is per **manager**, not per player, so every assertion here keys on
`owner_user_id` — the field `gather_rivals` already stamps on every row.
"""

from unittest.mock import patch

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import clausulazo_candidates as cands
from packages.biwenger_tools.api.logic import pact_store


def _row(bw_id, owner_user_id, name="Jugador"):
    return {
        "bw_id": bw_id,
        "name": name,
        "owner": f"Manager {owner_user_id}",
        "owner_user_id": owner_user_id,
        "position_id": 3,
        "clause_value": 10_000_000,
        "clausulable_now": True,
    }


# --- annotate_pact ---------------------------------------------------------


def test_annotate_pact_marks_only_the_pacted_managers_players():
    rows = [_row(1, 10), _row(2, 20), _row(3, 10)]
    cands.annotate_pact(rows, {10})
    assert [r["pacted"] for r in rows] == [True, False, True]


def test_annotate_pact_marks_every_row_even_with_an_empty_pact():
    """`pacted` is always present, so no caller has to guess a missing key."""
    rows = [_row(1, 10), _row(2, 20)]
    cands.annotate_pact(rows, set())
    assert [r["pacted"] for r in rows] == [False, False]


def test_annotate_pact_compares_ids_as_integers():
    """Firestore hands back whatever was written; Biwenger ids are ints. A
    pact stored as strings must still match, or the veto silently does
    nothing — the worst possible failure for this feature."""
    rows = [_row(1, 10)]
    cands.annotate_pact(rows, {"10"})
    assert rows[0]["pacted"] is True


# --- without_pacted --------------------------------------------------------


def test_without_pacted_drops_the_pacted_managers_players():
    rows = [_row(1, 10), _row(2, 20), _row(3, 10)]
    kept = cands.without_pacted(rows, {10})
    assert [r["bw_id"] for r in kept] == [2]


def test_without_pacted_returns_everything_when_the_pact_is_empty():
    rows = [_row(1, 10), _row(2, 20)]
    assert cands.without_pacted(rows, set()) == rows


def test_without_pacted_does_not_mutate_its_input():
    """`/recomendar` and `/emergencia` share one `gather_rivals` result in
    some flows; a filter that edited the list in place would strip the rows
    `/recomendar` is required to keep showing."""
    rows = [_row(1, 10), _row(2, 20)]
    cands.without_pacted(rows, {10})
    assert len(rows) == 2


# --- pact_store ------------------------------------------------------------


def test_the_pact_is_not_scoped_to_a_season():
    """A pact with a rival is a standing arrangement, not a season artefact.

    Keyed by season it would empty itself at the rollover — silently, and
    failing *open*: the first `/emergencia` of the new year would propose the
    friend the pact exists to protect. `rebuild_store` is season-scoped because
    a rebuild plan is genuinely ephemeral; this is not that.
    """
    with patch.object(pact_store.fs, "get_document", return_value=None) as read:
        pact_store.load()
    collection, doc_id = read.call_args.args
    assert collection == "pactos"
    assert doc_id == pact_store.DOCUMENT
    assert config.CURRENT_SEASON not in doc_id


def test_load_returns_an_empty_set_when_no_pact_was_ever_saved():
    """A missing document is the normal state of a league with no pact, not
    an error: every caller must be able to treat it as "attack anyone"."""
    with patch.object(pact_store.fs, "get_document", return_value=None):
        assert pact_store.load() == set()


def test_load_reads_the_stored_manager_ids_as_integers():
    with patch.object(
        pact_store.fs, "get_document", return_value={"manager_ids": ["10", 20]}
    ):
        assert pact_store.load() == {10, 20}


def test_load_survives_a_document_with_a_junk_id():
    """One unparseable id must not blind the whole pact — the remaining
    managers stay protected."""
    with patch.object(
        pact_store.fs, "get_document", return_value={"manager_ids": [10, "", None]}
    ):
        assert pact_store.load() == {10}


def test_toggle_adds_a_manager_that_was_not_in_the_pact():
    with patch.object(pact_store.fs, "get_document", return_value=None):
        with patch.object(pact_store.fs, "set_document") as saved:
            assert pact_store.toggle(10) is True
    _, _, document = saved.call_args.args
    assert document["manager_ids"] == [10]


def test_toggle_removes_a_manager_that_was_already_in_the_pact():
    with patch.object(
        pact_store.fs, "get_document", return_value={"manager_ids": [10, 20]}
    ):
        with patch.object(pact_store.fs, "set_document") as saved:
            assert pact_store.toggle(10) is False
    _, _, document = saved.call_args.args
    assert document["manager_ids"] == [20]


def test_toggle_returns_whether_the_manager_ended_up_protected():
    """The bot renders the new state straight from this boolean instead of
    re-reading, so it is the contract, not a convenience."""
    with patch.object(pact_store.fs, "get_document", return_value=None):
        with patch.object(pact_store.fs, "set_document"):
            assert pact_store.toggle(7) is True


# --- /recomendar shows pacted players, flagged ----------------------------


def _reco_row(bw_id, owner_user_id, pacted, sf=300):
    return {
        "bw_id": bw_id,
        "name": f"Jugador {bw_id}",
        "owner": f"Manager {owner_user_id}",
        "owner_user_id": owner_user_id,
        "position_id": 3,
        "alt_positions": [],
        "clause_value": 10_000_000,
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
        "pacted": pacted,
    }


def test_recommendations_keep_pacted_players_and_carry_the_flag():
    """The pact is advisory here: the owner still sees the whole market and
    decides. Hiding them would make `/recomendar` disagree with reality."""
    from packages.biwenger_tools.api.logic import recommendations as recs

    grouped = recs._pick_top_per_position(
        [_reco_row(1, 10, pacted=True, sf=900), _reco_row(2, 20, pacted=False, sf=100)],
        top=3,
    )
    assert [r["bw_id"] for r in grouped["MID"]] == [1, 2]
    assert [r["pacted"] for r in grouped["MID"]] == [True, False]


def test_recommendations_render_a_badge_for_a_pacted_player():
    from packages.biwenger_tools.api.logic import recommendations as recs

    text = recs._format_telegram_text(
        {
            "budget": {
                "cash": 1_000_000,
                "max_bid": 2_000_000,
                "margin": 2_000_000,
                "margin_source": "auto",
                "target": 3_000_000,
            },
            "recommendations": {
                "GK": [],
                "DEF": [],
                "MID": [
                    {
                        "bw_id": 1,
                        "name": "Pedri",
                        "owner": "Pablo",
                        "clause": 10_000_000,
                        "sf": 900,
                        "multi": [],
                        "pacted": True,
                    },
                    {
                        "bw_id": 2,
                        "name": "Gavi",
                        "owner": "Ana",
                        "clause": 9_000_000,
                        "sf": 800,
                        "multi": [],
                        "pacted": False,
                    },
                ],
                "FWD": [],
            },
        }
    )
    pedri = next(line for line in text.split("\n") if "Pedri" in line)
    gavi = next(line for line in text.split("\n") if "Gavi" in line)
    assert recs.PACT_BADGE in pedri
    assert recs.PACT_BADGE not in gavi


# --- /emergencia never proposes a pacted manager's player ------------------


def test_no_target_message_names_the_pact_when_it_is_what_emptied_the_pool():
    """The case that matters: a broken XI, cash in hand, and the only
    affordable rivals are friends. Blaming the budget would send the owner
    hunting for money they already have."""
    from packages.biwenger_tools.api.logic import emergency

    text = emergency._format_no_target_text("línea más débil", 5_000_000, excluded=3)
    assert "3" in text
    assert "pacto" in text.lower()


def test_no_target_message_stays_quiet_when_no_one_was_excluded():
    from packages.biwenger_tools.api.logic import emergency

    text = emergency._format_no_target_text("línea más débil", 5_000_000, excluded=0)
    assert "pacto" not in text.lower()
