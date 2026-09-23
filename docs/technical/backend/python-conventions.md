# Python in lillorepo — conventions

> **Summary.** Python in lillorepo has **one** dependency model: every
> third-party distribution resolves from `requirements_lock.txt`, and the
> production image is derived from that lock and checked against it. It has
> **one** shape for code: pure logic, a service, a thin route and a
> zero-logic bot, with failures that are loud rather than quiet. This page
> states that model as numbered rules, `LP-1` … `LP-24`. Each rule gives the
> reason it exists and **how conformance is checked**, so it is always clear
> which rules CI enforces and which depend on review.

This is not a generic guide: the baseline is PEP 8, PEP 20 and PEP 257, and
where they and this page disagree, this page wins. Every rule here exists
because something in this repo motivated it. A rule
that loses its motive gets changed or removed, and a rule that CI could check
but does not is a candidate for a check.

It complements `CLAUDE.md` (workflow, PRs) and `.claude/CLAUDE.md` (comment
policy) and does not repeat them. Examples cite real files; reading them is
worth more than any paragraph.

---

## Terms

- **Checked by**, the last line of every rule:
  - **`Lint`** / **`Test`**: the required CI checks on every pull request
    (`scripts/lint.sh` and the affected Bazel suites). A violation blocks the
    merge.
  - **Review**: nothing mechanical catches it. It holds because whoever
    writes or reviews the change reads this page. When one of these slips
    more than once, it gets a check.
- **Logic**: anything under `packages/*/*/logic/` or `core/`.
- **Script**: an operational or skill script run by hand, under
  `packages/*/scripts/` or `.claude/skills/*/scripts/`, never deployed.

Rules are cited by number (`LP-12`) in reviews, commit messages and code
comments.

---

## Dependencies

### LP-1 — One resolution point

Every third-party distribution SHALL resolve through the single `@pypi` hub
(`pip.parse` over `requirements_lock.txt` in `MODULE.bazel`). There SHALL be no
second hub, no second lock and no `pip install` at run time. The production
base image (`docker/Dockerfile.base`) installs every runtime package in the lock,
at the lock's version.

**Why.** Bazel runs the tests against the lock; Cloud Run runs whatever the
image installed. When the two disagree, every test is green and the service
dies with an `ImportError` at cold start, and there is no older revision with
the right dependencies to roll back to.

**Checked by:** `Lint`. `scripts/check_base_sync.py` fails when a runtime
package in the lock is missing from the image or pinned at another version.

### LP-2 — Every consumed distribution is declared directly

Every `@pypi//<name>` label in a `BUILD.bazel` SHALL correspond to a direct
line in some module's `requirements.txt`. A distribution that is only in the
lock as a transitive dependency SHALL be declared before it is consumed.

**Why.** A transitive pin is a version someone else's dependency chose. The
next regeneration can move it or drop it with no diff in any
`requirements.txt`, and nobody reviewing that regeneration knows a consumer
existed.

**Checked by:** `Lint`. `check_base_sync.py` reads every `@pypi//x` and
`requirement("x")` in the tracked BUILD and `.bzl` files and fails on any
distribution no module `requirements.txt` declares.

### LP-3 — The lock is generated; the image list is derived

Dependencies SHALL change only through the module `requirements.txt` →
regenerated `requirements.in` → `pip-compile` → `requirements_lock.txt` chain,
driven by the `add-python-dep` skill. Nobody edits `requirements.in` or the
lock by hand. The module `requirements.txt` files are **inputs** to the lock,
never copies of it, and `Dockerfile.base` is the only manifest derived from it.

**Why.** A manifest that the build does not consume cannot stay in sync
through discipline: it drifts, and every dependency tool recognises the file
name, so the drift gets acted on against versions that never ship. For the
same reason Dependabot is limited to GitHub Actions (`.github/dependabot.yml`
says why). A bot cannot drive this chain.

**Checked by:** `Lint`. `check_base_sync.py` also fails when a module's
`requirements.txt` is missing from `requirements.in`.

### LP-4 — A dependency change ships alone

A dependency bump or addition SHALL be its own pull request, one bump per
pull request where practical, never bundled with feature code.

**Why.** A bump changes the runtime of the whole image. Mixed with a feature,
a regression cannot be bisected, and the deploy that introduced it cannot be
reverted without losing the feature.

**Checked by:** review.

### LP-5 — Development environments derive from the lock

`bazel run` and `bazel test` are the development loop. When a plain
virtualenv is unavoidable (mutation testing, an IDE), every distribution the
code imports SHALL come from the lock: `pip install -r requirements_lock.txt`.
Standalone tools that are not in the lock and never imported by the code
(`pip-tools`, `mutmut`) are installed next to it, never instead of it. Docs and
scripts SHALL NOT tell anyone to `pip install` the project's own dependencies
by name.

**Why.** An environment resolved on its own gets whatever versions are
newest that day. What passes there has not been tested against what ships.

**Checked by:** review.

### LP-6 — `requests` and the stdlib first

Before adding a distribution, check whether `requests` and the standard
library already cover the need.

**Why.** Every distribution is a lock entry, an image layer and a future bump.
The GCS client in `core/sdk/gcp.py` talks to the JSON API with `requests`
precisely to avoid pulling in `google-cloud-storage` for two calls.

**Checked by:** review.

### Dependency lifecycle

- **Adding.** Apply LP-6 first, then the `add-python-dep` skill (LP-3), in a
  pull request of its own (LP-4).
- **Updating.** Same chain. `check-deps` shows what is behind. There is one
  version of each distribution for the whole repo; a package that cannot
  follow an upgrade is raised before the merge, not solved by a second pin.
- **Removing.** Delete the line from the module's `requirements.txt` once no
  `@pypi//<name>` consumes it, regenerate, and drop it from `Dockerfile.base`.
  Nothing flags an image that keeps installing it: `check_base_sync.py` checks
  that the image has what the lock needs, not that it has nothing more.

---

## Code shape

### LP-7 — Four layers, and the draft is the canon

| Layer | Example | May touch |
|---|---|---|
| Pure logic | `api/logic/draft.py` | nothing: no HTTP, no Firestore, no Telegram |
| Service | `api/logic/draft_service/` | persistence and clients; orchestrates the pure logic |
| HTTP route | `api/app.py` | request/response and a call to the service |
| Bot | `bot/app.py` | **zero business logic**: formats and forwards; the api answers with a ready-to-send `message` |

A client that more than one package needs lives in `core/sdk/` and carries
no business logic: it speaks a protocol. A client only one package needs may
live in that package, and the same rule applies to it.

**Why.** Pure logic is tested with no mocks, the service with small fakes, and
the route only pins the wiring. A bot that decides something duplicates a rule
the api already owns, and the two drift.

**Checked by:** review. The signal to look for: a logic test that needs
`MagicMock` means the layer is cut in the wrong place.

### LP-8 — Functions and dataclasses before classes

The default is pure functions plus `@dataclass` for state (`DraftState`,
`Pick`, `NameMatch`). A class exists only when there is real session state to
hold (`BiwengerClient` keeps auth and a `requests.Session`). There is no
inheritance between our own classes; composition is explicit.

**Why.** State that lives in arguments and return values can be tested
without constructing anything, which is what keeps the pure-logic layer of
LP-7 free of mocks.

**Checked by:** review.

### LP-9 — Shared code is a Bazel dependency, never a path

Code SHALL reach other code only through a `deps` edge in `BUILD.bazel`. No
`imports` entry SHALL escape its package, and deployed code SHALL NOT touch
`sys.path`. Scripts (LP-24) and tests are the exception: they bootstrap with
`sys.path.insert` so they run from the repo root with nothing installed.

**Why.** The affected-test selector in CI reasons over the Bazel graph
(`scripts/affected_tests.py`). An edge the graph does not know about is a
consumer CI will not re-test when its dependency changes.

**Checked by:** `Lint`. `scripts/check_import_paths.py` fails on an
`imports` entry containing `..` and on any `sys.path` mutation or
`site.addsitedir` outside scripts and tests.

### LP-10 — `core` holds only what genuinely crosses packages

Something enters `core/` when more than one package needs it. League-specific
facts (member ids, the draft order, the league id) live in the package that
owns the league, in `packages/biwenger_tools/constants.py`.

**Why.** A fact that two packages each write down ends up diverging, which
happened to the draft order. Anything in `core`'s shared base also rides into
every image that links any slice of it, and a Chuck Norris bot has no business
carrying a Biwenger roster.

**Checked by:** review, helped by the per-slice `core` targets. A package
links only the slices it uses.

---

## Failures

### LP-11 — Loud beats silent

A failure SHALL surface as an exception or an explicit error value, never as
an empty result that looks like data. Validate the **payload**, not just the
status code.

**Why.** JP answers an invalid token with HTTP 200 and `{"error": "auth"}`.
That parsed as an empty list, and the digest would have run on no data
(`core/sdk/jp.py::_raise_if_unhealthy`). "Nobody matched" and "the read broke"
call for opposite responses and must not look alike (`core/sdk/oraculo.py`).

**Checked by:** review, plus a test per SDK that pins the raise.

### LP-12 — Never retry a non-idempotent mutation

`retry_http_request` SHALL be used only for reads and for writes that carry an
idempotency key. A write without one goes through a single direct call, with a
comment citing this rule (`BiwengerClient._post_admin_operation`).

**Why.** Biwenger's admin endpoints answer an empty `204` with no key. A retry
after a timeout that actually succeeded charges twice.

**Checked by:** review, plus `call_count == 1` tests on every failing money
path (LP-22).

### LP-13 — Idempotency is built on our side, and writes are verified

Before calling an external service that moves something, reserve the action
in a deterministic Firestore document inside a transaction
(`draft_service._reserve_pick`). When the service answers an empty `204`,
re-read its state to confirm the write.

**Why.** Telegram retries webhooks, so every handler will eventually run twice.
And an empty `204` confirms nothing: re-reading is the only confirmation there
is.

**Checked by:** `Test`. The duplicate-call tests of LP-22.

### LP-14 — Every error reaches the person who asked

In the bot, every api error SHALL reach the chat through the one helper
(`_report_api_error`), HTML-escaped.

**Why.** An error message that itself breaks Telegram's HTML parser leaves the
user with no feedback at all, which is worse than the original error.

**Checked by:** review.

---

## Observability and documentation

### LP-15 — Structured logs, data in `extra`

Log with `core.utils.get_logger(__name__)`, which writes JSON to stdout.
Data SHALL go in `extra={...}`, never be interpolated into the message. No
`print` outside scripts.

**Why.** Cloud Logging indexes `extra` fields (`jsonPayload.chat_id=...`); an
f-string is only searchable as free text.

**Checked by:** review.

### LP-16 — Docstrings state contracts, types state shapes

The docstring states the contract; a comment exists only when the *why* is
not obvious. No dates, no history, no pull-request references in either (full
policy in `.claude/CLAUDE.md`, "no testaments"). Every public signature has
type hints, with an explicit `X | None` when the default is `None` and no
gratuitous `Any`.

**Why.** A comment that recounts history becomes false after the next
refactor, and two audits have already had to clean them out.

**Checked by:** review.

### LP-17 — Spanish for users, English for everything else

User-facing strings are Spanish. Code, logs, docstrings, comments and docs are
English.

**Why.** The league reads Spanish; the repo is public and read by people and
agents who do not.

**Checked by:** review.

---

## Tests

### LP-18 — The test comes first, and is seen failing

For logic, write the test, run it, confirm it fails *for the reason you
expect* (a wrong value, not an `ImportError` or a typo), and only then
implement until it passes. Paste both runs, the red one and the green one.

**Why.** A test written alongside its implementation is anchored to it and
reads green either way, so "a test asserting current behaviour is worthless
if current behaviour is the bug" cannot be checked after the fact. The red
run is the proof the test can fail at all. The scope is deliberate: route
glue, scripts (already governed by LP-24) and docs are excluded, because there
the loop costs time without paying off.

**Checked by:** review. Nothing in CI can prove a test predated its code, so
it is enforced the way every process rule here is: by pasting the output.

### LP-19 — Every module has a suite, and CI runs it

Every module SHALL have its Bazel test target (`//packages/.../x:x_tests`).
Pull requests run the suites the change can break; `master` runs all of them
before deploying.

**Why.** `master` deploys on every push, so a suite CI does not run is a
suite that does not protect production.

**Checked by:** `Test`.

### LP-20 — A spec and its test are a pair

Behaviour is stated in `openspec/` and proved by a test. A scenario without a
test is a gap; a test without a scenario is undocumented behaviour. Behaviour
changes update the spec in the same pull request.

**Why.** A spec that names a test which no longer exists claims coverage that
is not there, and the next reader trusts it.

**Checked by:** `Lint`. `scripts/check_specs.py` fails on a broken test
reference and warns on a scenario with no test.

### LP-21 — Mock at the boundary; never the network

Fakes sit at the edge: an in-memory `FakeFirestore`, `MagicMock` for the
Biwenger session, `_run_in_background` patched to run synchronously. Pure
logic is never mocked. Tests never touch the network. When a config default
points at a URL, the fixture redirects it to a local file; the path-over-URL
precedence of `DRAFT_MARKET_CSV_PATH` exists for this.

**Why.** A mock inside the logic tests the mock. A network call makes the
suite flaky and slow, and makes it depend on someone else's uptime.

**Checked by:** review.

### LP-22 — Every path that moves money has a duplicate-call test

Each such path SHALL have one test that "the second call does NOT reach the
external service" (`test_duplicate_applied_pick_does_not_recall_biwenger`) and
one that "a failing POST is issued exactly once" (`call_count == 1`).

**Why.** These are the only proof that LP-12 and LP-13 hold, and a mistake
there is paid in game money, not in a red build.

**Checked by:** `Test`, once the test exists. Writing it is review.

---

## Tooling and scripts

### LP-23 — One quality toolchain, run hermetically

Formatting is `black` and linting is `flake8` (`max-line-length = 88`),
both run through Bazel's Python 3.13 by `scripts/lint.sh`. Run
`bash scripts/lint.sh --fix` before pushing.

**Why.** `black` formats slightly differently across Python versions. Running
it with the maintainer's 3.12 against CI's 3.13 produced a string of fixup
commits. Moving to `ruff` is parked until it has a trigger
(`docs/technical/parked-work.md`).

**Checked by:** `Lint`.

### LP-24 — Scripts are dry-run by default

Scripts live under `packages/{package}/scripts/{domain}/`, grouped by what
they operate on (`draft/`, `scraper/`), so the file name only has to carry
the verb. They follow one pattern (`scripts/draft/reset.py`):

- **Dry-run by default, `--apply` to write.** The dry run shows what it would
  do, with counts. No exceptions.
- ADC (`gcloud auth application-default login`), never a key in the script.
- Bootstrap with `sys.path.insert(0, ...parents[N])`, sanctioned by LP-9
  for scripts and tests only.
- A script that deletes anything prints what it keeps and why (the draft
  reset keeps `managers` and says so).

**Why.** These scripts perform surgery on production Firestore. The dry run is
the review.

**Checked by:** review.

---

## Baseline — the generic rules that still bite

Not numbered, because nothing in this repo motivated them: they are Python's
own traps. Listed because they are what a reviewer still catches.

- **No mutable defaults.** `def f(items=[])` shares one list across every
  call. Use `None` and create the list inside.
- **No dead code, no commented-out code.** Delete it; `git` keeps it.
- **No circular imports.** Two modules importing each other means the
  boundary between them is in the wrong place. Move the shared piece down
  (to `core/` when two packages need it, LP-10), rather than hiding the cycle
  with an import inside a function.
- **Imports in three groups**, stdlib, third party, then local, one blank
  line apart. `flake8` does not enforce the order; `black` keeps the rest.
- **Names say what, not how.** `snake_case` functions and variables,
  `PascalCase` classes, `UPPER_CASE` module constants, a leading `_` for
  module-private helpers. Prefer renaming to commenting (LP-16).

## Deviations

With a single owner there is no allowlist. A deliberate deviation is written
**where it happens**, as a comment that cites the rule and gives the reason
(the direct POST in `BiwengerClient._post_admin_operation` is the model for
LP-12). An uncommented deviation is a defect. A rule that keeps being
deviated from gets rewritten here rather than argued with site by site.

## Enforcement at a glance

| Checked by | Rules |
|---|---|
| `Lint` | LP-1, LP-2, LP-3, LP-9, LP-20, LP-23 |
| `Test` | LP-13, LP-19, LP-22 |
| Review | LP-4, LP-5, LP-6, LP-7, LP-8, LP-10, LP-11, LP-12, LP-14, LP-15, LP-16, LP-17, LP-18, LP-21, LP-24 |

A review-only rule that slips more than once is the next candidate for a
check. The checks live in `scripts/` and run from `scripts/lint.sh`; their
decisions are tested in `//scripts:scripts_tests`.

---

## Appendix — stack traps

Learned, not theoretical. These are not rules; they are the environment the
rules run in.

- **`requests.text` with no declared charset decodes as ISO-8859-1** (per the
  RFC). A UTF-8 CSV served by GCS without a `content-type` loses every accent.
  Decode explicitly: `response.content.decode("utf-8-sig")`.
- **`source .env` in bash expands `$`**, so a token containing `$` gets
  silently truncated. `.env` files are read from Python, not from the shell.
- **Per-instance caches on Cloud Run** are fine for frozen data (the draft
  market), but re-uploading the object does NOT refresh warm instances.
  Document it wherever the object is operated.
- **`--set-env-vars` replaces the whole block** on deploy. An env var that
  must survive lives in a GitHub repository variable, not hand-set on Cloud
  Run.
- **gunicorn's 30 s worker timeout** kills a slow handler with SIGKILL before
  its `except` runs. Services with long handlers raise it through
  `core.serving.gunicorn.run(..., timeout=)`.
- **Telegram ids**: a chat with a negative id is a group, and user ids are
  always positive. Never derive one from the other.
