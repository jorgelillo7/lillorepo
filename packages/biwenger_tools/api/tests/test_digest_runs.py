"""Unit tests for `api/logic/digest_runs` — one digest per Madrid day, however
many times the trigger is delivered."""

from packages.biwenger_tools.api.logic import digest_runs


def test_a_day_with_no_run_yet_may_start():
    assert digest_runs.may_start({}, now=1_000.0)


def test_a_finished_run_blocks_the_day():
    assert not digest_runs.may_start({"status": "done", "started_at": 0}, now=10**9)


def test_a_run_under_way_blocks_a_duplicate_delivery():
    doc = {"status": "running", "started_at": 1_000.0}
    assert not digest_runs.may_start(doc, now=1_040.0)


def test_a_run_that_never_finished_stops_blocking_once_stale():
    doc = {"status": "running", "started_at": 1_000.0}
    assert digest_runs.may_start(doc, now=1_000.0 + digest_runs.STALE_S + 1)


def test_a_failed_run_may_be_retried():
    assert digest_runs.may_start({"status": "failed", "started_at": 1_000.0}, 1_001.0)
