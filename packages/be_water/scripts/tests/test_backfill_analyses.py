"""The one-shot backfill that seeds the analysis series.

It ran once against the real catalog and wrote eleven entries that had to be
repaired by hand afterwards, so the two properties that repair depended on are
pinned here: it copies no photos, and it never rewrites an entry that exists.
"""

from unittest.mock import patch

from packages.be_water.scripts import backfill_analyses
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.scripts.backfill_analyses.repository"


def _water(wid, date, **kwargs):
    return Water(
        id=wid,
        name=wid,
        brand=wid,
        spring="",
        province="Segovia",
        community="Castilla y León",
        analysis_date=date,
        minerals={"tds": 100},
        **kwargs,
    )


def _run(waters, existing=None, apply=True):
    argv = ["backfill_analyses"] + (["--apply"] if apply else [])
    with patch(f"{_MOD}.get_all_waters", return_value=waters), patch(
        f"{_MOD}.get_analysis", side_effect=lambda wid, d: (existing or {}).get(wid)
    ), patch(f"{_MOD}.save_analysis") as save, patch("sys.argv", argv):
        backfill_analyses.main()
    return save


def test_the_entry_takes_none_of_the_ficha_s_photos():
    """The ficha's photos live at the bare `{id}.jpg` path, which any later
    undated correction overwrites. Copied here, a dated entry would offer as
    proof of one year an image that quietly becomes another — which is exactly
    what happened to eleven entries."""
    save = _run(
        [_water("bezoya", "2024-01", photo_url="p.jpg", label_photo_url="l.jpg")]
    )

    entry = save.call_args.args[0]
    assert entry.photo_url is None
    assert entry.label_photo_url is None
    assert entry.minerals == {"tds": 100}, "todo lo demás sí viaja"


def test_an_undated_water_never_enters_the_series():
    """An undated composition can be the ficha's current one and still have no
    place on a timeline — three quarters of the catalog is in that state."""
    save = _run([_water("bezoya", None)])

    save.assert_not_called()


def test_rerunning_leaves_an_existing_entry_alone():
    """Idempotence is the whole reason it is safe to run twice: an entry that
    exists may since have been corrected by hand."""
    save = _run(
        [_water("bezoya", "2024-01")],
        existing={"bezoya": {"analysis_date": "2024-01"}},
    )

    save.assert_not_called()


def test_a_dry_run_writes_nothing():
    save = _run([_water("bezoya", "2024-01")], apply=False)

    save.assert_not_called()
