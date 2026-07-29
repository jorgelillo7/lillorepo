from packages.biwenger_tools.api.logic.player_matching import (
    build_jp_index,
    find_player_match,
)


def _jp(name: str, slug: str = "") -> dict:
    return {"name": name, "slug": slug}


def test_exact_match_still_works():
    jp_index = build_jp_index([_jp("Iago Aspas"), _jp("Rubén")])
    assert find_player_match("Iago Aspas", jp_index)["name"] == "Iago Aspas"


def test_unique_surname_match_still_works():
    """«Aspas» is a genuine one-to-one surname match and must keep working."""
    jp_index = build_jp_index(
        [_jp("Aspas"), _jp("Rubén")],
        biwenger_names=["Iago Aspas", "Rubén García"],
    )
    assert find_player_match("Iago Aspas", jp_index)["name"] == "Aspas"


def test_first_name_collision_ruben_returns_none_for_all_claimants():
    """Real shape: JP has a single mononym «Rubén»; three different
    Biwenger surnames all reduce to it via the first-name strategy. None
    of them should silently win it."""
    jp_index = build_jp_index(
        [_jp("Rubén")],
        biwenger_names=["Rubén García", "Rubén López", "Rubén Sánchez"],
    )
    assert find_player_match("Rubén García", jp_index) is None
    assert find_player_match("Rubén López", jp_index) is None
    assert find_player_match("Rubén Sánchez", jp_index) is None


def test_surname_collision_valverde_excludes_the_coach():
    """Real shape: JP has a single mononym «Valverde»; two different
    Biwenger surnames both reduce to it via the surname strategy. Neither
    should silently win it."""
    jp_index = build_jp_index(
        [_jp("Valverde")],
        biwenger_names=["Fernando Valverde", "Ernesto Valverde"],
    )
    assert find_player_match("Fernando Valverde", jp_index) is None
    assert find_player_match("Ernesto Valverde", jp_index) is None


def test_safe_match_blocks_a_lone_loose_claimant_on_the_same_target():
    """Real shape: Biwenger's «Valverde» exact-matches the JP mononym
    «Valverde»; the coach «Ernesto Valverde» is the only OTHER name that
    would reach it via the surname strategy — a single loose claimant, so
    it would look "unique" in isolation. It must still be rejected: the
    target already belongs to a real, safely-matched player."""
    jp_index = build_jp_index(
        [_jp("Valverde")],
        biwenger_names=["Valverde", "Ernesto Valverde"],
    )
    assert find_player_match("Valverde", jp_index)["name"] == "Valverde"
    assert find_player_match("Ernesto Valverde", jp_index) is None


def test_collision_does_not_affect_unrelated_players():
    jp_index = build_jp_index(
        [_jp("Rubén"), _jp("Aspas")],
        biwenger_names=["Rubén García", "Rubén López", "Iago Aspas"],
    )
    assert find_player_match("Rubén García", jp_index) is None
    assert find_player_match("Iago Aspas", jp_index)["name"] == "Aspas"


def test_ambiguity_check_is_skipped_without_full_roster():
    """Without `biwenger_names`, the cross-roster check can't run — a loose
    match still resolves via the single-key lookup, same as before."""
    jp_index = build_jp_index([_jp("Rubén")])
    assert find_player_match("Rubén García", jp_index)["name"] == "Rubén"


def test_token_subset_ambiguous_within_a_single_call_returns_none():
    """Two different JP full names both being supersets of the same token
    set is detectable without any roster context — reject outright."""
    jp_index = build_jp_index([_jp("Pedro Gonzalez Lopez"), _jp("Pedro Lopez Ruiz")])
    assert find_player_match("Pedro Lopez", jp_index) is None


def test_token_subset_unique_match_still_works():
    jp_index = build_jp_index([_jp("Pedro Gonzalez Lopez")])
    assert find_player_match("Pedro Lopez", jp_index)["name"] == "Pedro Gonzalez Lopez"


def test_override_resolved_names_do_not_join_the_collision_pool():
    """A name resolved via PLAYER_NAME_MAPPINGS never reaches the loose
    ladder, so it must not be able to poison another player's loose match."""
    jp_index = build_jp_index(
        [_jp("Vini Jr"), _jp("Rubén")],
        biwenger_names=["Vinicius Jr", "Rubén García"],
    )
    assert find_player_match("Vinicius Jr", jp_index)["name"] == "Vini Jr"
    assert find_player_match("Rubén García", jp_index)["name"] == "Rubén"


def test_no_match_returns_none():
    jp_index = build_jp_index([_jp("Iago Aspas")])
    assert find_player_match("Completely Unknown Player", jp_index) is None
