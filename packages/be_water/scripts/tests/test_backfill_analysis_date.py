"""The backfill that reads the analysis date off stored label photos.

A date written to the ficha alone left the water dated but outside its own
analysis series (aquadeus), so writing one seeds the series entry too.
"""

from unittest.mock import patch

from packages.be_water.scripts import backfill_analysis_date
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.scripts.backfill_analysis_date"


def _water(wid, label="gs://b/originals/x.jpg", date=None):
    return Water(
        id=wid,
        name=wid,
        brand=wid,
        spring="",
        province="Segovia",
        community="Castilla y León",
        minerals={"tds": 100},
        photo_url="gs://b/x.jpg",
        label_photo_url=label,
        analysis_date=date,
    )


def _run(waters, extracted, write=False, answers=("g",), existing=None):
    argv = ["backfill_analysis_date", "--delay", "0"] + (["--write"] if write else [])
    with (
        patch(f"{_MOD}.repository.get_all_waters", return_value=waters),
        patch(f"{_MOD}._read_label", return_value=extracted) as read,
        patch(f"{_MOD}._prompt", side_effect=list(answers)),
        patch(f"{_MOD}.repository.get_analysis", return_value=existing),
        patch(f"{_MOD}.repository.save_water") as save_water,
        patch(f"{_MOD}.repository.save_analysis") as save_analysis,
        patch("sys.argv", argv),
    ):
        backfill_analysis_date.main()
    return read, save_water, save_analysis


def test_a_dry_run_reads_but_writes_nothing():
    read, save_water, save_analysis = _run([_water("a")], {"analysis_date": "2025-02"})
    read.assert_called_once()
    save_water.assert_not_called()
    save_analysis.assert_not_called()


def test_only_undated_fichas_with_a_label_photo_are_read():
    waters = [_water("no-label", label=None), _water("dated", date="2024")]
    read, _, _ = _run(waters, {"analysis_date": "2025-02"})
    read.assert_not_called()


def test_a_label_that_prints_no_date_writes_nothing():
    _, save_water, save_analysis = _run(
        [_water("a")], {"analysis_date": None}, write=True
    )
    save_water.assert_not_called()
    save_analysis.assert_not_called()


def test_writing_a_date_seeds_the_series_entry_without_photos():
    _, save_water, save_analysis = _run(
        [_water("a")], {"analysis_date": "2025-02"}, write=True
    )
    assert save_water.call_args.args[0].analysis_date == "2025-02"
    entry = save_analysis.call_args.args[0]
    assert entry.analysis_date == "2025-02"
    assert entry.photo_url is None
    assert entry.label_photo_url is None


def test_an_existing_series_entry_is_left_alone():
    _, save_water, save_analysis = _run(
        [_water("a")], {"analysis_date": "2025-02"}, write=True, existing={"x": 1}
    )
    save_water.assert_called_once()
    save_analysis.assert_not_called()


def test_skipping_writes_nothing():
    _, save_water, save_analysis = _run(
        [_water("a")], {"analysis_date": "2025-02"}, write=True, answers=("s",)
    )
    save_water.assert_not_called()
    save_analysis.assert_not_called()
