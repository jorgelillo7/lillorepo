"""Tests for the two python-conventions rules the linters cannot see.

LP-2 (every consumed distribution is declared directly) and LP-9 (shared code
is a Bazel dependency, never a path) both held by habit before they had a
check. These pin the decisions, not the file walking: that runs for real in
`scripts/lint.sh` on every pull request.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_base_sync as sync  # noqa: E402
import check_import_paths as paths  # noqa: E402

# --- LP-2: consumed labels vs. direct declarations ---


def test_a_label_declared_directly_passes():
    build = 'deps = ["@pypi//google_cloud_firestore", requirement("flask")]'
    assert sync.consumed_distributions(build) == {"google-cloud-firestore", "flask"}


def test_the_hub_file_itself_is_not_a_distribution():
    assert sync.consumed_distributions('load("@pypi//:requirements.bzl", "r")') == set()


def test_a_dotted_name_matches_its_label():
    """rules_python turns `zope.interface` into `@pypi//zope_interface`."""
    assert sync.canonical("zope.interface") == sync.canonical("zope_interface")


def test_a_transitive_only_label_is_reported():
    """`urllib3` is in the lock because `requests` pulls it in. Consuming it
    without declaring it leaves its version to someone else's resolution."""
    undeclared = sync.undeclared_labels(
        {"BUILD.bazel": 'deps = ["@pypi//requests", "@pypi//urllib3"]'},
        declared={"requests"},
    )
    assert undeclared == [("BUILD.bazel", "urllib3")]


# --- LP-9: sys.path and escaping imports ---


def test_deployed_code_touching_sys_path_is_reported():
    for line in (
        "sys.path.insert(0, root)",
        "sys.path.append(root)",
        "sys.path.extend([root])",
        "sys.path += [root]",
        "sys.path = [root]",
        "sys.path[:0] = [root]",
        "site.addsitedir(root)",
    ):
        assert paths.mutates_sys_path(line), line


def test_mentioning_sys_path_is_not_touching_it():
    """A docstring saying the launcher needs no `sys.path` tricks is fine."""
    assert not paths.mutates_sys_path("resolves without sys.path tricks.")
    assert not paths.mutates_sys_path("    # sys.path.insert would break this")
    assert not paths.mutates_sys_path("print(sys.path)")
    assert not paths.mutates_sys_path("first = sys.path[0]")


def test_scripts_and_tests_may_bootstrap_sys_path():
    """Scripts run by hand from the repo root are the sanctioned exception."""
    for allowed in (
        "packages/biwenger_tools/scripts/draft/reset.py",
        "packages/biwenger_tools/.claude/skills/draft/scripts/board.py",
        ".claude/skills/audit-apple-contacts/scripts/apply.py",
        "scripts/tests/test_affected_tests.py",
        "packages/be_water/web/tests/test_routes.py",
    ):
        assert paths.may_touch_sys_path(allowed), allowed
    assert not paths.may_touch_sys_path("packages/biwenger_tools/api/app.py")
    assert not paths.may_touch_sys_path("core/sdk/jp.py")


def test_an_imports_entry_escaping_its_package_is_reported():
    assert paths.escaping_imports('imports = ["..", "src"]') == [".."]
    assert paths.escaping_imports('imports = ["../../core"]') == ["../../core"]
    assert paths.escaping_imports('imports = ["src"]') == []
