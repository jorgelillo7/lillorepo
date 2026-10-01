"""Tests for the coverage summary CI prints on every pull request."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coverage_report as cr  # noqa: E402

LCOV = """\
SF:core/a.py
DA:1,1
LF:10
LH:8
end_of_record
SF:packages/biwenger_tools/api/logic/b.py
LF:20
LH:10
end_of_record
SF:core/a.py
LF:10
LH:9
end_of_record
"""


def test_records_of_the_same_file_keep_the_best_count():
    """One file instrumented by two suites: the union is at least the best one."""
    cov = cr.parse_lcov(LCOV)
    assert cov["core/a.py"] == (10, 9)
    assert cov["packages/biwenger_tools/api/logic/b.py"] == (20, 10)


def test_files_no_test_imports_are_listed_not_hidden():
    """A file missing from the report is invisible, not covered — say so."""
    cov = cr.parse_lcov(LCOV)
    sources = ["core/a.py", "packages/biwenger_tools/api/logic/b.py", "core/c.py"]
    summary = cr.summarise(cov, sources)
    assert summary.invisible == ["core/c.py"]
    assert (summary.lines, summary.hit) == (30, 19)


def test_areas_group_by_package_module():
    cov = cr.parse_lcov(LCOV)
    summary = cr.summarise(cov, ["core/a.py", "packages/biwenger_tools/api/logic/b.py"])
    assert summary.areas == {
        "core": (10, 9),
        "packages/biwenger_tools/api": (20, 10),
    }


def test_a_file_at_a_package_root_belongs_to_its_package():
    assert cr.area_of("packages/biwenger_tools/constants.py") == "packages/biwenger_tools"
    assert cr.area_of("scripts/check_specs.py") == "scripts"


def test_sources_skip_tests_inits_and_vendored_skills():
    files = [
        "core/a.py",
        "core/__init__.py",
        "core/tests/test_a.py",
        "packages/x/web/tests/main.py",
        "scripts/test_y.py",
        ".claude/skills/google-cloud-run-basics/x.py",
        "README.md",
    ]
    assert cr.source_files(files) == ["core/a.py"]


def test_the_markdown_names_the_totals_and_the_invisible_files():
    cov = cr.parse_lcov(LCOV)
    md = cr.render(cr.summarise(cov, ["core/a.py", "core/c.py"]), suites=["//core:t"])
    assert "63.3 %" in md  # 19 / 30
    assert "`core/c.py`" in md
    assert "//core:t" in md


def test_an_empty_report_fails_loudly():
    """No data means the coverage step broke, not that nothing needs testing."""
    with pytest.raises(ValueError, match="no coverage records"):
        cr.parse_lcov("")
