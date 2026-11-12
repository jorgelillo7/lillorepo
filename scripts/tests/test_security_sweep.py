"""Tests for the security sweep, against a throwaway git repository.

Every planted secret is assembled at runtime from fragments, so this file holds
no literal credential for GitHub push protection, `check_url_secrets.py` or the
sweep itself to find. `gh`, `npm` and OSV are faked; only `git` really runs.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import security_sweep as sweep

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

FAKE_AWS = "AK" + "IA" + "FAKEFAKE" + "12345678"
FAKE_PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"
FAKE_TOKEN = "gh" + "p_" + "Q" * 36
FAKE_SA = '{"type": "service' + '_account", "project_id": "demo"}'
INJECTION = "${{ github.event." + "pull_request.title }}"


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "HOME": str(repo),
    }
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=repo, env=env, check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip


def commit(repo: Path, files: dict[str, str | bytes | None], message: str) -> None:
    for name, content in files.items():
        path = repo / name
        if content is None:
            git(repo, "rm", "-q", name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


WORKFLOW = f"""name: PR
on:
  pull_request_target:
    branches: [main]
permissions:
  contents: write
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@{"a" * 40}
      - run: |
          echo "{INJECTION}"
      - run: echo safe
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    commit(root, {"README.md": "hello\n", ".gitignore": "secrets/\n"}, "init")
    commit(root, {"config.ini": f"aws_key = {FAKE_AWS}\n"}, "add config")
    commit(root, {"config.ini": "aws_key = ${AWS_KEY}\n"}, "move key out")
    commit(root, {"app/release.jks": b"\x00\x01binary"}, "keystore")
    commit(root, {".github/workflows/pr.yml": WORKFLOW}, "ci")
    commit(root, {"inbox/movements.txt": f"token {FAKE_TOKEN}\n"}, "private data")
    (root / "secrets").mkdir()
    (root / "secrets" / "deploy-sa.json").write_text(FAKE_SA)
    (root / "secrets" / "creds.json").write_text(FAKE_SA)
    (root / "notes.txt").write_text(f"{FAKE_PEM}\n")
    return root


class Offline(sweep.System):
    """Real git; canned answers for everything that would leave the machine."""

    def __init__(self, *, tools: tuple[str, ...] = ("gh", "npm")) -> None:
        self.tools = tools
        self.gh: dict[str, Any] = {}
        self.npm = "{}"
        self.osv: dict[str, Any] = {}
        self.calls: list[list[str]] = []

    def which(self, tool: str) -> str | None:
        return f"/fake/{tool}" if tool in self.tools else None

    def run(self, cmd: list[str], cwd: Path) -> tuple[int, str]:
        self.calls.append(cmd)
        if cmd[0] == "gh":
            if cmd[1] == "repo":
                return 0, json.dumps(
                    {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}}
                )
            answer = self.gh.get(cmd[-1])
            return (0, json.dumps(answer)) if answer is not None else (1, "")
        if cmd[0] == "npm":
            return 1, self.npm
        return super().run(cmd, cwd)

    def http(self, url: str, body: dict[str, Any] | None = None) -> Any:
        if body is not None:
            return {
                "results": [
                    self.osv.get(q["package"]["name"], {}) for q in body["queries"]
                ]
            }
        return self.osv[url.rsplit("/", 1)[1]]


def rules(report: sweep.Report, step: str) -> dict[str, list[sweep.Finding]]:
    out: dict[str, list[sweep.Finding]] = {}
    for f in report.findings:
        if f.step == step:
            out.setdefault(f.rule, []).append(f)
    return out


def test_a_key_removed_from_the_tree_is_still_found_in_history(repo: Path) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    [aws] = rules(report, "secrets")["aws-access-key"]
    assert aws.path == "config.ini"
    assert aws.commit == git(repo, "log", "--format=%H", "-1", "HEAD~4")[:12]
    assert aws.masked == FAKE_AWS[:4] + "…"


def test_uncommitted_files_are_scanned_too(repo: Path) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    [pem] = rules(report, "secrets")["private-key"]
    assert (pem.path, pem.commit) == ("notes.txt", "working tree")


def test_a_committed_keystore_name_is_reported(repo: Path) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    paths = [f.path for f in rules(report, "secrets")["key-file-committed"]]
    assert paths == ["app/release.jks"]


def test_an_excluded_path_never_reaches_any_step(repo: Path) -> None:
    system = Offline()
    report = sweep.sweep(system, repo, ["inbox"], offline=True)
    assert not any(f.path.startswith("inbox") for f in report.findings)
    assert "github-token" not in rules(report, "secrets")
    git_calls = [c for c in system.calls if c[0] == "git" and "--" in c]
    assert all(":(exclude)inbox" in c for c in git_calls)


def test_without_the_exclusion_the_private_file_would_have_been_found(
    repo: Path,
) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    [token] = rules(report, "secrets")["github-token"]
    assert token.path == "inbox/movements.txt"


def test_ignored_key_files_are_listed_by_path_only(repo: Path) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    found = sorted(f.path for f in rules(report, "ignored")["ignored-key-file"])
    assert found == ["secrets/creds.json", "secrets/deploy-sa.json"]
    assert all(f.masked == "" for f in report.findings if f.step == "ignored")


def test_no_secret_value_is_ever_printed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for flags in ([], ["--json"]):
        assert sweep.main([str(repo), "--offline", *flags], Offline()) == 1
        out = capsys.readouterr().out
        for value in (FAKE_AWS, FAKE_TOKEN, FAKE_PEM, "service" + "_account"):
            assert value not in out


def test_the_allowlist_silences_by_fingerprint_and_by_path(repo: Path) -> None:
    first = sweep.sweep(Offline(), repo, [], offline=True)
    failing = {f.path: f.fingerprint for f in first.failing()}
    allow = repo / sweep.ALLOWLIST_NAME
    allow.write_text(
        f"{failing['config.ini']}  # fake key in a fixture\n"
        "path:app/*.jks\npath:inbox/*\npath:notes.txt\n"
    )
    report = sweep.sweep(Offline(), repo, [], offline=True)
    assert report.failing() == []
    assert sweep.main([str(repo), "--offline"], Offline()) == 0


def test_workflow_injection_unpinned_actions_and_pr_target(repo: Path) -> None:
    report = sweep.sweep(Offline(), repo, [], offline=True)
    found = rules(report, "workflows")
    assert [f.path for f in found["pull-request-target"]] == [
        ".github/workflows/pr.yml:3"
    ]
    assert [f.path for f in found["script-injection"]] == [
        ".github/workflows/pr.yml:14"
    ]
    assert [f.detail for f in found["unpinned-action"]] == [
        "actions/checkout@v4 is not pinned to a SHA"
    ]
    [write] = found["pr-write-permissions"]
    assert (write.path, write.severity) == (".github/workflows/pr.yml:6", "high")


def test_a_push_only_workflow_with_write_permission_passes() -> None:
    text = "on:\n  push:\npermissions:\n  contents: write\njobs: {}\n"
    assert list(sweep.workflow_findings("w.yml", text)) == []


def test_injection_outside_run_is_not_reported() -> None:
    text = f"on: [pull_request]\njobs:\n  a:\n    if: {INJECTION}\n"
    assert not [
        f
        for f in sweep.workflow_findings("w.yml", text)
        if f.rule == "script-injection"
    ]


def test_placeholders_are_not_secrets() -> None:
    for line in (
        "storePassword = System.getenv('STORE_PASSWORD')",
        'storePassword = props["storePassword"]',
        "https://user:${PASSWORD}@example.com",
        "Authorization: Bearer $TOKEN",
        "aws_key = ${AWS_KEY}",
    ):
        assert list(sweep.scan_text(line)) == [], line


def test_literal_store_passwords_and_url_credentials_are_secrets() -> None:
    password = "hunt" + "er22"
    assert [r.name for r, _ in sweep.scan_text(f'storePassword "{password}"')] == []
    assert [r.name for r, _ in sweep.scan_text(f'storePassword = "{password}"')] == [
        "store-password"
    ]
    pair = "admin" + ":" + "s3cretpw"
    assert [r.name for r, _ in sweep.scan_text(f"https://{pair}@db.example")] == [
        "url-credentials"
    ]


def test_python_pins_and_gradle_catalog_are_read() -> None:
    lock = "requests[socks]==2.32.0 \\\n    --hash=sha256:x\n# via foo\nflask>=3\n"
    assert sweep.python_pins(lock) == [("requests", "2.32.0")]
    catalog = """
[versions]
kotlin = "2.0.0"
[libraries]
a = { group = "org.x", name = "a", version.ref = "kotlin" }
b = { module = "org.y:b", version = "1.2" }
c = "org.z:c:3.4"
bom-managed = { group = "androidx.compose.ui", name = "ui" }
"""
    coords, unversioned = sweep.gradle_coordinates(catalog)
    assert coords == [("org.x:a", "2.0.0"), ("org.y:b", "1.2"), ("org.z:c", "3.4")]
    assert unversioned == 1


def test_a_critical_osv_advisory_fails_and_an_unrated_one_does_not(
    repo: Path,
) -> None:
    commit(
        repo,
        {"requirements_lock.txt": "jinja2==2.0\nrequests==2.0\n"},
        "lock",
    )
    system = Offline(tools=())
    system.osv = {
        "jinja2": {"vulns": [{"id": "GHSA-crit"}]},
        "requests": {"vulns": [{"id": "PYSEC-unrated"}]},
        "GHSA-crit": {
            "summary": "sandbox escape",
            "database_specific": {"severity": "CRITICAL"},
            "affected": [
                {
                    "package": {"name": "jinja2"},
                    "ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.1"}]}],
                }
            ],
        },
        "PYSEC-unrated": {},
    }
    report = sweep.sweep(system, repo, ["inbox"], offline=False)
    deps = {f.rule: f for f in report.findings if f.step == "deps"}
    assert deps["GHSA-crit"].severity == "critical"
    assert "fixed in 2.1" in deps["GHSA-crit"].detail
    assert deps["PYSEC-unrated"].severity == "unrated"
    assert deps["GHSA-crit"] in report.failing()
    assert deps["PYSEC-unrated"] not in report.failing()


def test_a_missing_tool_skips_its_step_with_a_line(repo: Path) -> None:
    commit(repo, {"web/package-lock.json": "{}"}, "lock")
    report = sweep.sweep(Offline(tools=()), repo, [], offline=False)
    assert "github: skipped (gh is not installed)" in report.notes
    assert "deps: skipped npm audit (npm is not installed)" in report.notes


def test_npm_audit_reads_the_lock_only(repo: Path) -> None:
    commit(repo, {"web/package-lock.json": "{}"}, "lock")
    system = Offline(tools=("npm",))
    system.npm = json.dumps(
        {
            "vulnerabilities": {
                "vite": {
                    "severity": "critical",
                    "range": "<5.0.1",
                    "via": [{"title": "path traversal"}],
                    "fixAvailable": True,
                }
            }
        }
    )
    report = sweep.sweep(system, repo, [], offline=False)
    [npm] = [f for f in report.findings if f.rule == "npm-audit"]
    assert (npm.severity, npm.path) == ("critical", "web/package-lock.json")
    assert ["npm", "audit", "--json", "--package-lock-only"] in system.calls


def test_github_settings_are_read_without_writing(repo: Path) -> None:
    system = Offline(tools=("gh",))
    system.gh = {
        "repos/o/r": {
            "security_and_analysis": {
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "disabled"},
            }
        },
        "repos/o/r/dependabot/alerts?state=open&per_page=100": [
            {
                "number": 7,
                "security_advisory": {"severity": "critical", "summary": "rce"},
                "dependency": {"package": {"ecosystem": "npm", "name": "x"}},
            }
        ],
        "repos/o/r/actions/permissions/workflow": {
            "default_workflow_permissions": "write"
        },
        "repos/o/r/environments": {
            "environments": [
                {"name": "production", "deployment_branch_policy": None},
                {"name": "pages", "deployment_branch_policy": {"x": True}},
            ]
        },
    }
    report = sweep.sweep(system, repo, [], offline=False)
    found = {f.rule: f for f in report.findings if f.step == "github"}
    assert set(found) == {
        "branch-protection",
        "secret-scanning-push-protection",
        "dependabot-7",
        "actions-token",
        "environment-branches",
    }
    assert "production" in found["environment-branches"].detail
    assert found["dependabot-7"] in report.failing()
    for call in system.calls:
        if call[:2] == ["gh", "api"]:
            assert call[2:4] == ["-X", "GET"]
            assert not {"-f", "-F", "--field", "--raw-field"} & set(call)


def test_a_run_block_ends_where_its_indentation_does() -> None:
    text = (
        "on: [pull_request]\njobs:\n  a:\n    steps:\n"
        "      - run: |\n          echo hi\n"
        f"      - if: {INJECTION}\n        run: echo later\n"
    )
    assert not [
        f
        for f in sweep.workflow_findings("w.yml", text)
        if f.rule == "script-injection"
    ]
