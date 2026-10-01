"""Tests for the check that keeps code under test out of `py_test` srcs."""

from scripts import check_test_srcs as check


def test_code_under_test_listed_in_a_test_target_is_reported():
    """Bazel does not instrument a test target's own files: coverage goes blank."""
    labels = [
        "//scripts:tests/test_affected_tests.py",
        "//scripts:tests/main.py",
        "//scripts:affected_tests.py",
        "//packages/x/web:tests/conftest.py",
        "//packages/x/api:test_helpers.py",
    ]
    assert check.misplaced(labels) == ["//scripts:affected_tests.py"]


def test_non_python_sources_are_ignored():
    assert check.misplaced(["//scripts:tests/data.json", "//a:b.txt"]) == []
