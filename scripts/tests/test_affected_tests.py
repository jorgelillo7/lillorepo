"""Tests for the CI test-selection logic.

This script decides which suites run. A bug here does not fail loudly — it
silently runs nothing, and the PR goes green having verified less than it
looks. That makes it exactly the kind of code the draft skill's tests were
written for: a wrong answer that still looks like an answer.

Only the pure decisions are covered. `query_tests` shells out to Bazel and is
exercised for real on every CI run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import affected_tests as at  # noqa: E402


# --- The safety net: changes rdeps cannot see must run everything ---


def test_a_bzl_change_forces_everything():
    """The macro every service loads is not a target, so `rdeps` reports it
    affects nothing. That is the shape of a change that rewrites every image."""
    assert at.forces_everything("tools/bazel/python_service.bzl")


def test_build_and_module_files_force_everything():
    for path in (
        "packages/biwenger_tools/api/BUILD.bazel",
        "MODULE.bazel",
        "MODULE.bazel.lock",
        "requirements_lock.txt",
        "core/requirements.txt",
        ".bazelrc",
        ".bazelversion",
    ):
        assert at.forces_everything(path), path


def test_ci_changes_force_everything():
    """Editing the workflow or this selector must re-run the suite it decides,
    or the decision itself goes unverified."""
    assert at.forces_everything(".github/workflows/ci.yml")
    assert at.forces_everything("scripts/affected_tests.py")


def test_ordinary_sources_and_docs_do_not_force_everything():
    for path in (
        "packages/be_water/web/app.py",
        "docs/README.md",
        "PENDING.md",
        "packages/biwenger_tools/api/logic/lineup.py",
    ):
        assert not at.forces_everything(path), path


# --- Mapping a file to the package that owns it ---


def test_a_source_file_maps_to_its_nearest_package():
    assert at.label_for("packages/be_water/web/app.py") == (
        "//packages/be_water/web:app.py"
    )


def test_a_nested_source_maps_to_the_package_above_it():
    """`routes/` has no BUILD.bazel of its own, so it belongs to `web`."""
    assert at.label_for("packages/biwenger_tools/web/routes/main.py") == (
        "//packages/biwenger_tools/web:routes/main.py"
    )


def test_files_outside_every_package_map_to_nothing():
    """Docs are in no Bazel package, which is what makes a documentation
    change run no tests at all."""
    assert at.label_for("docs/README.md") is None
    assert at.label_for("PENDING.md") is None
