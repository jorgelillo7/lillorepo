"""Sweep one or more repositories for leaked secrets, risky settings and advisories.

Usage:
    python3 scripts/security_sweep.py [REPO ...] [--exclude PATHSPEC ...]
                                      [--allowlist FILE] [--offline] [--json]

Each repository (default: the one the current directory is in) gets five steps:

  secrets     the working tree and every commit of `git log --all -p` scanned
              for credential shapes, plus every file name ever committed that
              looks like a key, a keystore or an env file
  ignored     key files sitting in the working tree though git-ignored
  deps        Python pins and the Gradle catalog through OSV; `npm audit` in
              each directory with a package-lock.json
  github      repository settings, read through `gh api` (GET only)
  workflows   risky patterns in .github/workflows

Secret values are never printed: each is masked to its first four characters
and identified by a fingerprint, which is what the allowlist holds. Paths given
with --exclude are kept out of every step, so a repository holding private data
can be swept without its files or their diffs ever being read.

The allowlist (default: `.security-sweep-allowlist` at the repository root)
holds one entry per line: a fingerprint, or `path:<glob>` to accept every
finding under matching paths; `#` starts a comment.

Exit status: 1 when a secret or a critical advisory is found and not
allowlisted, 0 otherwise. The deps and github steps call the network; with
--offline they are skipped.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/"
ALLOWLIST_NAME = ".security-sweep-allowlist"
MAX_SCAN_BYTES = 2_000_000
SNIFF_BYTES = 4096
BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2",
    ".ttf", ".otf", ".zip", ".gz", ".jar", ".aar", ".apk", ".aab", ".so", ".jks",
    ".keystore", ".p12", ".mp3", ".mp4", ".webm",
)  # fmt: skip

# Severity of a finding. The first two fail the run.
FAILING = ("secret", "critical")


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    # A marker matches the same text everywhere (a PEM header, a JSON key), so
    # its fingerprint is taken from the path instead of the value.
    marker: bool = False


def _rule(name: str, regex: str, *, marker: bool = False, flags: int = 0) -> Rule:
    return Rule(name, re.compile(regex, flags), marker)


SECRET_RULES = (
    _rule(
        "private-key",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?"
        r"PRIVATE KEY(?: BLOCK)?-----",
        marker=True,
    ),
    _rule("google-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _rule(
        "github-token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})"
    ),
    _rule("slack-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    _rule(
        "slack-webhook",
        r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
    ),
    _rule("service-account", r'"type"\s*:\s*"service_account"', marker=True),
    _rule("service-account", r'"private_key_id"\s*:\s*"[0-9a-f]{40}"', marker=True),
    _rule(
        "store-password",
        r"""(?:store|key)Password\s*[=:]\s*["']([^"'$\s{}<]{4,})["']""",
    ),
    _rule(
        "store-password",
        r"^\s*(?:store|key)Password\s*=\s*([^\s\"'$<{]{4,})\s*$",
    ),
    _rule("bearer-token", r"\b[Bb]earer\s+([A-Za-z0-9\-._~+/]{20,}=*)"),
    _rule("telegram-bot-token", r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"),
    _rule("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    _rule(
        "aws-secret-key",
        r"""aws_secret_access_key\s*[=:]\s*["']?([A-Za-z0-9/+=]{40})""",
        flags=re.IGNORECASE,
    ),
    _rule(
        "url-credentials",
        r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"<>]+:"
        r"(?![<{$%*]|x{3}|password\b|pass\b)([^\s:/@'\"<>]{3,})@",
        flags=re.IGNORECASE,
    ),
    _rule(
        "url-credentials",
        r"https?://[^\s'\"`)<>]*?[?&]"
        r"(?:auth|token|access_token|api_?key|apikey|secret|password)="
        r"(?![<{$%*]|\.\.\.|x{3}|your)([^&\s'\"`)<>\]]{6,})",
        flags=re.IGNORECASE,
    ),
    _rule("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)

# File names that should never have been committed, matched on the basename.
KEY_FILE_NAMES = (
    "*.jks",
    "*.keystore",
    "keystore.properties",
    ".env",
    ".env.*",
    "*.pem",
    "*.p12",
    "google-services.json",
    ".dev.vars",
    "*service-account*.json",
    "*service_account*.json",
    "*-sa.json",
    "*-sa-key*.json",
)
# Templates that only show the shape of an env file.
KEY_FILE_TEMPLATES = (".env.example", ".env.sample", ".env.template", ".env.dist")
SKIPPED_DIRS = ("node_modules", ".gradle", "build", "venv", ".venv", "__pycache__")


@dataclass
class Finding:
    step: str
    severity: str
    rule: str
    path: str = ""
    detail: str = ""
    commit: str = ""
    masked: str = ""
    fingerprint: str = ""
    allowlisted: bool = False


@dataclass
class Report:
    repo: str
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def failing(self) -> list[Finding]:
        return [f for f in self.findings if f.severity in FAILING and not f.allowlisted]


class System:
    """Every call that leaves the process. Tests replace it to run offline."""

    def which(self, tool: str) -> str | None:
        return shutil.which(tool)

    def run(self, cmd: list[str], cwd: Path) -> tuple[int, str]:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return done.returncode, done.stdout

    def lines(self, cmd: list[str], cwd: Path) -> Iterator[str]:
        with subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
        ) as proc:
            assert proc.stdout is not None
            yield from proc.stdout

    def http(self, url: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


# ── helpers ──────────────────────────────────────────────────────────────────


def mask(value: str) -> str:
    return value[:4] + "…"


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:12]


def exclude_specs(excludes: Iterable[str]) -> list[str]:
    return [f":(exclude){e.rstrip('/')}" for e in excludes]


def is_excluded(path: str, excludes: Iterable[str]) -> bool:
    for e in excludes:
        e = e.rstrip("/")
        if path == e or path.startswith(e + "/") or fnmatch.fnmatch(path, e):
            return True
    return False


def is_key_file_name(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in KEY_FILE_TEMPLATES:
        return False
    return any(fnmatch.fnmatch(name, p) for p in KEY_FILE_NAMES)


def in_skipped_dir(path: str) -> bool:
    return any(part in SKIPPED_DIRS for part in PurePosixPath(path).parts[:-1])


def scan_text(line: str) -> Iterator[tuple[Rule, str]]:
    """Each `(rule, value)` a line matches; value is the secret, not the line."""
    for rule in SECRET_RULES:
        for match in rule.pattern.finditer(line):
            yield rule, match.group(match.lastindex or 0)


def load_allowlist(path: Path) -> tuple[set[str], list[str]]:
    prints: set[str] = set()
    globs: list[str] = []
    if not path.is_file():
        return prints, globs
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.split("#", 1)[0].strip()
        if entry.startswith("path:"):
            globs.append(entry[len("path:") :].strip())
        elif entry:
            prints.add(entry)
    return prints, globs


# ── step: secrets ────────────────────────────────────────────────────────────


def _secret_finding(rule: Rule, value: str, path: str, commit: str) -> Finding:
    key = path if rule.marker else value
    return Finding(
        step="secrets",
        severity="secret",
        rule=rule.name,
        path=path,
        commit=commit,
        masked=mask(value),
        fingerprint=fingerprint(rule.name, key),
    )


def scan_history(system: System, repo: Path, excludes: list[str]) -> Iterator[Finding]:
    """Secrets added by any commit on any ref, oldest commit reported."""
    cmd = [
        "git", "log", "--all", "-p", "--no-ext-diff", "--no-textconv",
        "--no-color", "--format=commit %H", "--", ".", *exclude_specs(excludes),
    ]  # fmt: skip
    seen: dict[tuple[str, str], Finding] = {}
    commit = path = ""
    for line in system.lines(cmd, repo):
        if line.startswith("commit "):
            commit = line.split()[1][:12]
        elif line.startswith("+++ "):
            target = line[4:].rstrip("\n")
            path = target[2:] if target.startswith("b/") else ""
        elif line.startswith("+") and path:
            for rule, value in scan_text(line[1:]):
                finding = _secret_finding(rule, value, path, commit)
                # `git log` walks newest first, so the last one seen is the
                # commit that introduced it.
                seen[(finding.fingerprint, path)] = finding
    yield from seen.values()


def scan_tree(system: System, repo: Path, excludes: list[str]) -> Iterator[Finding]:
    """Secrets in files not yet committed (tracked or untracked, never ignored)."""
    code, out = system.run(
        ["git", "ls-files", "-mo", "--exclude-standard", "--", ".",
         *exclude_specs(excludes)],
        repo,
    )  # fmt: skip
    if code != 0:
        return
    for path in out.splitlines():
        file = repo / path
        if path.endswith(BINARY_SUFFIXES) or not file.is_file():
            continue
        if file.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            for rule, value in scan_text(line):
                yield _secret_finding(rule, value, path, "working tree")


def committed_key_files(
    system: System, repo: Path, excludes: list[str]
) -> Iterator[Finding]:
    code, out = system.run(
        ["git", "log", "--all", "--diff-filter=A", "--name-only",
         "--format=commit %H", "--", ".", *exclude_specs(excludes)],
        repo,
    )  # fmt: skip
    if code != 0:
        return
    first: dict[str, str] = {}
    commit = ""
    for line in out.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:12]
        elif line and is_key_file_name(line):
            first[line] = commit
    for path, commit in first.items():
        yield Finding(
            step="secrets",
            severity="secret",
            rule="key-file-committed",
            path=path,
            commit=commit,
            fingerprint=fingerprint("key-file-committed", path),
            detail="a key, keystore or env file name was committed",
        )


# ── step: ignored key files ──────────────────────────────────────────────────


def _looks_like_service_account(file: Path) -> bool:
    try:
        with file.open("rb") as handle:
            head = handle.read(SNIFF_BYTES)
    except OSError:
        return False
    return b'"service_account"' in head or b'"private_key_id"' in head


def ignored_key_files(
    system: System, repo: Path, excludes: list[str]
) -> Iterator[Finding]:
    """Key files git ignores but the working tree holds: path only."""
    code, out = system.run(
        ["git", "ls-files", "-oi", "--exclude-standard", "--", ".",
         *exclude_specs(excludes)],
        repo,
    )  # fmt: skip
    if code != 0:
        return
    for path in out.splitlines():
        if in_skipped_dir(path):
            continue
        named = is_key_file_name(path)
        sniffed = (
            not named
            and path.endswith(".json")
            and _looks_like_service_account(repo / path)
        )
        if named or sniffed:
            yield Finding(
                step="ignored",
                severity="info",
                rule="ignored-key-file",
                path=path,
                fingerprint=fingerprint("ignored-key-file", path),
                detail="git-ignored, but on disk: keep it out of synced folders",
            )


# ── step: dependency advisories ──────────────────────────────────────────────

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\#]+)")


def python_pins(text: str) -> list[tuple[str, str]]:
    pins = []
    for line in text.splitlines():
        match = PIN.match(line.strip())
        if match:
            pins.append((match.group(1).lower(), match.group(2)))
    return pins


def gradle_coordinates(text: str) -> tuple[list[tuple[str, str]], int]:
    """`(group:name, version)` for each catalog library, and how many had none.

    A library without a version is managed by a BOM; OSV cannot be asked about
    it by name alone.
    """
    catalog = tomllib.loads(text)
    versions = catalog.get("versions", {})
    found: list[tuple[str, str]] = []
    unversioned = 0
    for entry in catalog.get("libraries", {}).values():
        if isinstance(entry, str):
            parts = entry.split(":")
            if len(parts) == 3:
                found.append((f"{parts[0]}:{parts[1]}", parts[2]))
            else:
                unversioned += 1
            continue
        module = entry.get("module") or f"{entry.get('group')}:{entry.get('name')}"
        version = entry.get("version")
        if isinstance(version, dict):
            ref = version.get("ref")
            version = versions.get(ref) if ref else version.get("strictly")
        if isinstance(version, str):
            found.append((module, version))
        else:
            unversioned += 1
    return found, unversioned


def _severity_of(vuln: dict[str, Any]) -> str:
    """OSV's database rating, lowercased; `unrated` when it gives none."""
    rating = (vuln.get("database_specific") or {}).get("severity")
    if not isinstance(rating, str):
        return "unrated"
    rating = rating.lower()
    return "medium" if rating == "moderate" else rating


def _fixed_in(vuln: dict[str, Any], name: str) -> str:
    for affected in vuln.get("affected", []):
        if (affected.get("package") or {}).get("name", "").lower() != name.lower():
            continue
        for range_ in affected.get("ranges", []):
            for event in range_.get("events", []):
                if "fixed" in event:
                    return str(event["fixed"])
    return ""


def osv_findings(
    system: System, packages: list[tuple[str, str, str, str]]
) -> Iterator[Finding]:
    """Advisories for `(ecosystem, name, version, source file)` packages."""
    details: dict[str, dict[str, Any]] = {}
    for start in range(0, len(packages), 500):
        chunk = packages[start : start + 500]
        queries = [
            {"package": {"ecosystem": eco, "name": name}, "version": version}
            for eco, name, version, _ in chunk
        ]
        answer = system.http(OSV_BATCH, {"queries": queries})
        for (eco, name, version, source), result in zip(
            chunk, answer.get("results", [])
        ):
            for hit in result.get("vulns") or []:
                vid = hit["id"]
                if vid not in details:
                    details[vid] = system.http(OSV_VULN + vid)
                vuln = details[vid]
                fixed = _fixed_in(vuln, name)
                yield Finding(
                    step="deps",
                    severity=_severity_of(vuln),
                    rule=vid,
                    path=source,
                    detail=f"{eco} {name} {version}"
                    + (f", fixed in {fixed}" if fixed else "")
                    + (f" — {vuln['summary']}" if vuln.get("summary") else ""),
                    fingerprint=fingerprint(vid, name, version),
                )


def npm_findings(system: System, repo: Path, lockfile: str) -> Iterator[Finding]:
    directory = PurePosixPath(lockfile).parent
    # --package-lock-only reads the lock alone: nothing installed, no scripts.
    _, out = system.run(
        ["npm", "audit", "--json", "--package-lock-only"], repo / directory
    )
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        yield Finding(
            step="deps",
            severity="info",
            rule="npm-audit",
            path=lockfile,
            detail="npm audit gave no JSON",
        )
        return
    for name, vuln in sorted((report.get("vulnerabilities") or {}).items()):
        titles = [v.get("title") for v in vuln.get("via", []) if isinstance(v, dict)]
        fix = vuln.get("fixAvailable")
        yield Finding(
            step="deps",
            severity=str(vuln.get("severity", "unrated")),
            rule="npm-audit",
            path=lockfile,
            detail=f"npm {name} {vuln.get('range', '')}"
            + (f" — {titles[0]}" if titles and titles[0] else "")
            + ("" if fix else " (no fix available)"),
            fingerprint=fingerprint("npm", lockfile, name, str(vuln.get("range"))),
        )


def dependency_step(
    system: System, repo: Path, excludes: list[str], report: Report
) -> None:
    code, out = system.run(
        ["git", "ls-files", "-co", "--exclude-standard", "--", ".",
         *exclude_specs(excludes)],
        repo,
    )  # fmt: skip
    files = [p for p in out.splitlines() if not in_skipped_dir(p)] if code == 0 else []

    packages: list[tuple[str, str, str, str]] = []
    for path in files:
        name = PurePosixPath(path).name
        text_file = repo / path
        if fnmatch.fnmatch(name, "requirements*.txt") and text_file.is_file():
            for pkg, version in python_pins(text_file.read_text(encoding="utf-8")):
                packages.append(("PyPI", pkg, version, path))
        elif name == "libs.versions.toml" and text_file.is_file():
            coords, unversioned = gradle_coordinates(
                text_file.read_text(encoding="utf-8")
            )
            packages += [("Maven", c, v, path) for c, v in coords]
            if unversioned:
                report.notes.append(
                    f"deps: {unversioned} catalog libraries in {path} have no "
                    "version (BOM-managed) and were not checked"
                )
    if packages:
        try:
            report.findings += osv_findings(system, packages)
            report.notes.append(f"deps: {len(packages)} pins checked against OSV")
        except OSError as error:
            report.notes.append(f"deps: skipped OSV ({error})")
    else:
        report.notes.append("deps: no Python pins or Gradle catalog")

    locks = [p for p in files if PurePosixPath(p).name == "package-lock.json"]
    if not locks:
        return
    if not system.which("npm"):
        report.notes.append("deps: skipped npm audit (npm is not installed)")
        return
    for lock in locks:
        report.findings += npm_findings(system, repo, lock)
    report.notes.append(f"deps: npm audit run on {len(locks)} lockfile(s)")


# ── step: GitHub settings ────────────────────────────────────────────────────


def gh_get(system: System, repo: Path, endpoint: str) -> Any:
    """`gh api` as a GET; None when GitHub answers 403 or 404.

    No `-f`/`-F` flag ever: either one silently turns the call into a POST.
    """
    code, out = system.run(["gh", "api", "-X", "GET", endpoint], repo)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def github_step(system: System, repo: Path, report: Report) -> None:
    if not system.which("gh"):
        report.notes.append("github: skipped (gh is not installed)")
        return
    code, out = system.run(
        ["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"], repo
    )
    if code != 0:
        report.notes.append("github: skipped (no GitHub remote gh can see)")
        return
    view = json.loads(out)
    slug = view["nameWithOwner"]
    branch = (view.get("defaultBranchRef") or {}).get("name", "main")

    def add(severity: str, rule: str, detail: str) -> None:
        report.findings.append(
            Finding(
                step="github",
                severity=severity,
                rule=rule,
                path=slug,
                detail=detail,
                fingerprint=fingerprint(slug, rule, detail),
            )
        )

    protection = gh_get(system, repo, f"repos/{slug}/branches/{branch}/protection")
    rulesets = gh_get(system, repo, f"repos/{slug}/rules/branches/{branch}") or []
    if protection is None and not rulesets:
        add("high", "branch-protection", f"{branch} has no protection or ruleset")

    meta = gh_get(system, repo, f"repos/{slug}") or {}
    security = meta.get("security_and_analysis")
    if security is None:
        report.notes.append("github: secret scanning settings not visible")
    else:
        for key, label in (
            ("secret_scanning", "secret scanning"),
            ("secret_scanning_push_protection", "push protection"),
        ):
            if (security.get(key) or {}).get("status") != "enabled":
                add("medium", key.replace("_", "-"), f"{label} is off")

    alerts = gh_get(
        system, repo, f"repos/{slug}/dependabot/alerts?state=open&per_page=100"
    )
    if alerts is None:
        report.notes.append("github: Dependabot alerts not visible")
    for alert in alerts or []:
        advisory = alert.get("security_advisory") or {}
        package = (alert.get("dependency") or {}).get("package") or {}
        add(
            str(advisory.get("severity", "unrated")).replace("moderate", "medium"),
            f"dependabot-{alert.get('number')}",
            f"{package.get('ecosystem', '')} {package.get('name', '')} — "
            f"{advisory.get('summary', '')}",
        )

    perms = gh_get(system, repo, f"repos/{slug}/actions/permissions/workflow")
    if perms is None:
        report.notes.append("github: default Actions token permission not visible")
    elif perms.get("default_workflow_permissions") == "write":
        add("medium", "actions-token", "the default GITHUB_TOKEN can write")
    if perms and perms.get("can_approve_pull_request_reviews"):
        add("low", "actions-approve", "workflows can approve pull requests")

    envs = gh_get(system, repo, f"repos/{slug}/environments")
    for env in (envs or {}).get("environments", []):
        if env.get("deployment_branch_policy") is None:
            add(
                "medium",
                "environment-branches",
                f"environment {env.get('name')} can be deployed from any branch",
            )


# ── step: workflows ──────────────────────────────────────────────────────────

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?([^'\"\s#]+)")
RUN = re.compile(r"^(\s*)(?:-\s+)?run:\s*(.*)$")
INJECTABLE = re.compile(r"\$\{\{\s*github\.(?:event\.[^}]*|head_ref)\s*\}\}")
KEY = re.compile(r"^(\s*)(?:-\s+)?([A-Za-z_][\w-]*|\"on\"|'on'):(.*)$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _triggers(lines: list[str]) -> str:
    """The text of the top-level `on:` section."""
    out: list[str] = []
    inside = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if _indent(line) == 0:
            inside = bool(re.match(r"^(?:on|\"on\"|'on'|true):", line))
            if inside:
                out.append(line.split(":", 1)[1])
            continue
        if inside:
            out.append(line)
    return " ".join(out)


def workflow_findings(path: str, text: str) -> Iterator[Finding]:
    lines = text.splitlines()
    triggers = _triggers(lines)
    pr_target = "pull_request_target" in triggers
    pr_triggered = pr_target or re.search(r"\bpull_request\b", triggers) is not None

    def finding(severity: str, rule: str, number: int, detail: str) -> Finding:
        return Finding(
            step="workflows",
            severity=severity,
            rule=rule,
            path=f"{path}:{number}",
            detail=detail,
            fingerprint=fingerprint(rule, path, detail),
        )

    if pr_target:
        number = next(
            i for i, line in enumerate(lines, 1) if "pull_request_target" in line
        )
        yield finding(
            "high",
            "pull-request-target",
            number,
            "runs with secrets and a write token on code from forks",
        )

    run_indent: int | None = None
    perm_indent: int | None = None
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if run_indent is not None and stripped and _indent(line) <= run_indent:
            run_indent = None
        if perm_indent is not None and stripped and _indent(line) <= perm_indent:
            perm_indent = None

        uses = USES.match(line)
        if uses:
            ref = uses.group(1)
            if not ref.startswith(("./", "docker://")):
                version = ref.rpartition("@")[2] if "@" in ref else ""
                if not re.fullmatch(r"[0-9a-f]{40}", version):
                    yield finding(
                        "low",
                        "unpinned-action",
                        number,
                        f"{ref} is not pinned to a SHA",
                    )

        run = RUN.match(line)
        if run:
            run_indent = _indent(line) + (2 if line.lstrip().startswith("-") else 0)
            body = run.group(2)
        elif run_indent is not None:
            body = line
        else:
            body = ""
        for match in INJECTABLE.finditer(body):
            yield finding(
                "high",
                "script-injection",
                number,
                f"{match.group(0)} expanded inside run:",
            )

        key = KEY.match(line)
        if key and key.group(2) == "permissions":
            value = key.group(3).strip()
            if value:
                if pr_triggered and "write" in value:
                    yield finding(
                        "high" if pr_target else "medium",
                        "pr-write-permissions",
                        number,
                        f"permissions: {value} on a pull-request workflow",
                    )
            else:
                perm_indent = _indent(line)
        elif perm_indent is not None and re.search(r":\s*write\b", line):
            if pr_triggered:
                yield finding(
                    "high" if pr_target else "medium",
                    "pr-write-permissions",
                    number,
                    f"{stripped} on a pull-request workflow",
                )


def workflow_step(repo: Path, excludes: list[str], report: Report) -> None:
    directory = repo / ".github" / "workflows"
    if not directory.is_dir():
        report.notes.append("workflows: none")
        return
    files = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    for file in files:
        rel = file.relative_to(repo).as_posix()
        if is_excluded(rel, excludes):
            continue
        report.findings += workflow_findings(rel, file.read_text(encoding="utf-8"))
    report.notes.append(f"workflows: {len(files)} checked")


# ── driver ───────────────────────────────────────────────────────────────────


def sweep(
    system: System,
    repo: Path,
    excludes: list[str],
    allowlist: Path | None = None,
    offline: bool = False,
) -> Report:
    report = Report(repo=str(repo))
    if system.run(["git", "rev-parse", "--git-dir"], repo)[0] != 0:
        report.notes.append("not a git repository: skipped")
        return report

    found = {
        (f.rule, f.fingerprint, f.path): f for f in scan_tree(system, repo, excludes)
    }
    for f in scan_history(system, repo, excludes):
        found.setdefault((f.rule, f.fingerprint, f.path), f)
    report.findings += found.values()
    report.findings += committed_key_files(system, repo, excludes)
    report.findings += ignored_key_files(system, repo, excludes)

    if offline:
        report.notes.append("deps, github: skipped (--offline)")
    else:
        dependency_step(system, repo, excludes, report)
        github_step(system, repo, report)
    workflow_step(repo, excludes, report)

    prints, globs = load_allowlist(allowlist or repo / ALLOWLIST_NAME)
    for f in report.findings:
        plain = f.path.split(":", 1)[0]
        if f.fingerprint in prints or any(fnmatch.fnmatch(plain, g) for g in globs):
            f.allowlisted = True
    return report


ORDER = ("secret", "critical", "high", "medium", "low", "unrated", "info")


def render(report: Report) -> str:
    out = [f"== {report.repo}"]
    shown = sorted(
        (f for f in report.findings if not f.allowlisted),
        key=lambda f: (ORDER.index(f.severity) if f.severity in ORDER else 9, f.step),
    )
    for f in shown:
        where = f.path + (f" @ {f.commit}" if f.commit else "")
        what = f.masked and f"{f.masked} [{f.fingerprint}]" or f.detail
        out.append(f"  {f.severity:<8} {f.step:<9} {f.rule}: {where}  {what}".rstrip())
    allowed = len(report.findings) - len(shown)
    if not shown:
        out.append("  no findings")
    if allowed:
        out.append(f"  ({allowed} allowlisted)")
    out += [f"  · {note}" for note in report.notes]
    return "\n".join(out)


def main(argv: list[str] | None = None, system: System | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repos", nargs="*", type=Path, default=[Path(".")])
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATH",
        help="keep this path out of every step (repeatable)",
    )
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    system = system or System()

    reports = []
    for path in args.repos:
        code, top = system.run(["git", "rev-parse", "--show-toplevel"], path)
        repo = Path(top.strip()) if code == 0 else path.resolve()
        reports.append(sweep(system, repo, args.exclude, args.allowlist, args.offline))

    failing = sum(len(r.failing()) for r in reports)
    if args.json:
        print(
            json.dumps(
                {
                    "failing": failing,
                    "repos": [
                        {
                            "repo": r.repo,
                            "findings": [asdict(f) for f in r.findings],
                            "notes": r.notes,
                        }
                        for r in reports
                    ],
                },
                indent=2,
            )
        )
    else:
        print("\n\n".join(render(r) for r in reports))
        print(
            f"\n{failing} secret(s) or critical advisories"
            if failing
            else "\nno secret and no critical advisory"
        )
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
