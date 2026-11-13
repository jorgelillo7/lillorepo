"""The backfill that records AESAN identity sources on existing fichas."""

from unittest.mock import patch

from packages.be_water.scripts import backfill_sources
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.scripts.backfill_sources"


def _water(wid, sources=None):
    return Water(
        id=wid,
        name=wid,
        brand=wid,
        spring="",
        province="Cuenca",
        community="Castilla-La Mancha",
        sources=sources or {},
    )


def _derive(water):
    return {**water.sources, "province": "aesan"}


def _run(waters, apply):
    argv = ["backfill_sources"] + (["--apply"] if apply else [])
    with (
        patch(f"{_MOD}.repository.get_all_waters", return_value=waters),
        patch(f"{_MOD}.provenance.derive_sources", side_effect=_derive),
        patch(f"{_MOD}.repository.set_water_sources") as write,
        patch("sys.argv", argv),
    ):
        backfill_sources.main()
    return write


def test_a_dry_run_writes_nothing():
    write = _run([_water("a")], apply=False)
    write.assert_not_called()


def test_only_fichas_whose_sources_change_are_written():
    waters = [_water("gap"), _water("done", sources={"province": "aesan"})]
    write = _run(waters, apply=True)
    write.assert_called_once_with("gap", {"province": "aesan"})
