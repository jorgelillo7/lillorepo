# 🛠️ Operations — lillorepo

Repo-wide runbook: the workflows that are the **same across every package**
(prerequisites, dependency management, secrets, linting, GCP cost/cleanup).

Per-package commands (run, test, Docker, deploy per module) live next to the
code they operate:

| Package | Runbook |
|---|---|
| `biwenger_tools` (web · scraper · api · bot) | [`packages/biwenger_tools/OPERATIONS.md`](../packages/biwenger_tools/OPERATIONS.md) |
| `be_water` (public waters catalog) | [`packages/be_water/OPERATIONS.md`](../packages/be_water/OPERATIONS.md) |
| `chucknorris_bot` | [`packages/chucknorris_bot/OPERATIONS.md`](../packages/chucknorris_bot/OPERATIONS.md) |

Season rollover and Firestore maintenance scripts (biwenger-specific) live in
the `biwenger_tools` runbook above. For the Firestore data model itself, see
[`firestore.md`](firestore.md).

📜 Index

- [📋 Prerequisites](#-prerequisites)
- [🧪 Core (shared library) tests](#-core-shared-library-tests)
- [📦 How to Add or Update Python Dependencies](#-how-to-add-or-update-python-dependencies)
- [🔐 Secrets Management](#-secrets-management)
- [💅 Linter and Auto-formatter](#-linter-and-auto-formatter)
- [🎯 Which tests CI runs](#-which-tests-ci-runs)
- [🧹 GCP Cleanup and Cost Control](#-gcp-cleanup-and-cost-control)
- [⚠️ Important Notes](#️-important-notes)

---

## 📋 Prerequisites

Before you start, make sure you have the following installed:

  * **Python 3.13** on the host, only for the stdlib scripts under `scripts/`
    (Bazel brings its own 3.13 for everything else)
  * **Visual Studio Code** with the [Bazel (The Bazel Team)](https://marketplace.visualstudio.com/items?itemName=BazelBuild.vscode-bazel) extension.
  * **Command-line tools:**
    ```bash
      brew install bazelisk
      brew install buildifier
    ```
  * **Google Cloud deployment:**
  ```bash
    gcloud auth login
    gcloud config set project biwenger-tools   # be_water deploys to project be-water-app
    gcloud auth configure-docker europe-southwest1-docker.pkg.dev
  ```

Full machine setup lives in [`setup/mac-setup.md`](setup/mac-setup.md). If you
run long Claude Code sessions, [`setup/long-running-sessions.md`](setup/long-running-sessions.md)
covers keeping them alive across a dropped connection or an idle Mac.

**Important note:** Bazel manages all Python dependencies hermetically — no venv is needed to run, test, or build. A venv is only required for `pip-tools` (used to regenerate the lock file) and for IDE integration (linting, autocomplete).

  ```bash
    # Only needed for dependency management and IDE support
    python3 -m venv venv
    source venv/bin/activate
    pip install pip-tools
  ```

## 🧪 Core (shared library) tests

`core` is shared by every package (Biwenger/JP SDKs, GCP, Telegram, Gemini,
domain models, utils). Run its suite with:

```bash
  bazel test //core:core_tests --test_output=streamed --test_arg=-v
  bazel test //core:core_tests --test_output=streamed --test_arg=-v --cache_test_results=no
```

## 📊 Test coverage

Line coverage is collected via the `coverage` tool bundled with rules_python
(enabled by `configure_coverage_tool` in `MODULE.bazel`; it never ships in the
runtime image). Run it across every target and produce a combined LCOV report:

```bash
  bazel coverage //... --combined_report=lcov --test_output=errors
```

The combined report lands at `$(bazel info output_path)/_coverage/_coverage_report.dat`
(standard LCOV: `SF:` per file, `DA:` per line). Aggregate it per package or
repo-wide with any LCOV reader, or `genhtml` it for a browsable report.
Coverage is a weak signal on its own — pair it with the behaviour specs in
`openspec/specs/` (what must be true) rather than chasing the percentage.

### Mutation testing (ad-hoc)

Coverage says a line *ran*; mutation testing says a bug in it would be *caught*.
It is run ad-hoc on pure-logic modules (not in CI — it is slow), in a throwaway
venv since it needs a plain pytest environment:

```bash
  python3 -m venv /tmp/mutenv
  # Same pins the tests and the image use (python-conventions LP-5).
  /tmp/mutenv/bin/pip install -r requirements_lock.txt 'mutmut<3'

  # from the repo root, mutate one module, run only its test file
  PYTHONPATH=. /tmp/mutenv/bin/mutmut run \
    --paths-to-mutate packages/biwenger_tools/api/logic/auto_bid.py \
    --runner "/tmp/mutenv/bin/python -m pytest \
      packages/biwenger_tools/api/tests/test_auto_bid.py -x -q -p no:cacheprovider"

  /tmp/mutenv/bin/mutmut results   # list survivors; `mutmut show <id>` to inspect
```

Triage survivors: most are equivalent mutants (log strings, internal dict keys)
— **do not** chase those. Kill the ones that reveal an untested behavioural
boundary. Auto-bid's pilot sits at ~70% (the surviving 30% are cosmetic).

## 📦 How to Add or Update Python Dependencies

The rules are `LP-1` … `LP-6` in
[`technical/backend/python-conventions.md`](technical/backend/python-conventions.md#dependencies);
the procedure is the **`add-python-dep` skill**, which walks every layer. This
section is the map, plus the two commands you need when running a step by hand.

| # | Layer | Updated by |
|---|---|---|
| 1 | `[module]/requirements.txt` | You: the unpinned name, **above** the `# dev-only` marker in `core/requirements.txt` for a runtime library, below it for a dev tool |
| 2 | `requirements.in` | Concatenation, below. Never by hand |
| 3 | `requirements_lock.txt` | `pip-compile`, below. Never by hand |
| 4 | The consuming `BUILD.bazel` | `@pypi//<name>`, hyphens become underscores, on the most specific target (table below) |
| 5 | `docker/Dockerfile.base`, then the `python-base` image and its digest in `MODULE.bazel` | The exact pin from the lock, alphabetical; then rebuild, push and update the digest (the skill has the commands) |

`scripts/check_base_sync.py` checks every layer against the others in `Lint`
except the image rebuild itself, so a step skipped by hand fails the pull
request instead of shipping an `ImportError`. A dependency change goes in a pull request of its own (LP-4).

### Regenerate the central `requirements.in`

From the repo root:

```bash
{
  for req_file in core/requirements.txt \
    packages/biwenger_tools/scraper_job/requirements.txt \
    packages/biwenger_tools/api/requirements.txt \
    packages/biwenger_tools/bot/requirements.txt \
    packages/biwenger_tools/web/requirements.txt \
    packages/chucknorris_bot/bot/requirements.txt \
    packages/be_water/web/requirements.txt; do
    echo; echo "# From: $req_file"; cat "$req_file"
  done
} > requirements.in
```

### Regenerate the lock file

```bash
pip-compile requirements.in -o requirements_lock.txt
```

### Which `core` target declares it

`core/BUILD.bazel` exposes one target per module, so a library reaches only the
packages that link that slice:

| Target | When to add here |
|---|---|
| `//core:biwenger` · `:domain` · `:firestore` · `:gcp` · `:gemini` · `:http` · `:jp` · `:oraculo` · `:serving` · `:telegram` · `:web` | Library used by the matching `sdk/`, `domain/`, `serving/` or `web/` module |
| `//core:_init` (private) | Library used by `utils.py` or `constants.py` — **every** slice deps on it, so a dependency added here reaches every package |
| `//core` (umbrella) | Never add here: it holds no sources, only the other targets |

Then `bazel build //...` and `bash scripts/lint.sh` to confirm.

## 🔐 Secrets Management

  * **Local development:** Use `.env` files at the root of each module.
  * **Production:** Use **Google Secret Manager**.

### Examples: creating secrets in GCP
```bash
# Create a secret from a file (e.g. service account)
gcloud secrets create biwenger-tools-sa-regional \
  --data-file="biwenger-tools-sa.json" \
  --replication-policy="user-managed" \
  --locations="$REGION"

# Create secrets from the command line
echo -n "YOUR_EMAIL@gmail.com" | gcloud secrets create biwenger-email-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "YOUR_PASSWORD" | gcloud secrets create biwenger-password-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"

echo -n "DRIVE_FOLDER_ID" | gcloud secrets create gdrive-folder-id-regional \
  --data-file=- \
  --replication-policy="user-managed" \
  --locations="$REGION"
```

### Updating a secret

Rotating is two commands, not one. **Destroy the version you replaced** —
Secret Manager bills a version while it is Enabled *or* Disabled, and the free
tier is 6 active versions across the whole billing account, not per project.
Disabling does not free the slot; only destroying does.

```bash
# 1. add the new value (becomes `latest`, which is what every deploy binds)
gcloud secrets versions add <secret-name> --project=<project> --data-file=-

# 2. redeploy so running instances pick it up, verify it works, then:
gcloud secrets versions destroy <old-version> --secret=<secret-name> --project=<project>
```

`scripts/check-gcp-costs.sh` prints the account-wide total and flags 🚨 when it
goes over. It only reports — nothing prunes versions automatically, so step 2
is on you. `telegram-bot-config-regional` accumulated three versions this way
before anyone noticed.

## 💅 Linter and Auto-formatter

Flake8 (linter) and Black (formatter) run as the required **`Lint`** check on
every pull request (`.github/workflows/ci.yml`) and again on every push to
`master`, where the `lint` job in `.github/workflows/deploy.yml` blocks `test`
and the deploy.

Editor and CLI usage, pinned versions, and how to upgrade live in
[`setup/linter.md`](setup/linter.md).

Quick local invocation (same hermetic Python 3.13 toolchain as CI — no
version drift, no pip install needed):

```bash
bash scripts/lint.sh         # check
bash scripts/lint.sh --fix   # apply black in place
```

Under the hood: `bazel run //tools/lint:black -- ...` and `//tools/lint:flake8`.
The first invocation is slow (Bazel resolves the lint targets); subsequent
calls are cached.

`scripts/lint.sh` also runs **`scripts/check_base_sync.py`**, which is not a
linter but guards the same class of mistake. Bazel resolves
`requirements_lock.txt` for tests while production runs whatever
`docker/Dockerfile.base` pip-installs; drift between them ships as green tests
and an `ImportError` at cold start. It checks that every module's
`requirements.txt` reaches `requirements.in`, that every runtime package in the
lock is installed in the image, and that the versions match. Runtime versus dev
is read from pip-compile's own `# via` annotations and the `# dev-only` marker
in `core/requirements.txt` — never from a list in the script, which would rot
exactly like the thing it guards.

`scripts/lint.sh` also runs **`scripts/check_specs.py`**, which keeps
`openspec/` honest. Each scenario names the test that verifies it, and nothing
checked that wiring — a spec naming a renamed test claims coverage that is not
there. A broken reference **fails**; a scenario with no test only **warns**,
because whether one is worth writing is a judgement and a gate would invite a
test written to satisfy the gate.

It also runs **`scripts/check_import_paths.py`** (python-conventions LP-9):
an `imports` entry that climbs out of its package, or deployed code mutating
`sys.path`, is an edge the Bazel graph cannot see, so the test selector below
would not re-test that consumer. Scripts and tests are exempt; they bootstrap
`sys.path` to run from the repo root. `check_base_sync.py` also enforces LP-2:
every `@pypi//x` a BUILD file consumes is declared in a module
`requirements.txt`.

## 🎯 Which tests CI runs

Pull requests run only the suites a change can break;
`.github/workflows/deploy.yml` still runs `//...` on `master`, so the branch
that deploys always verifies everything.

The selection comes from the build graph, not from a list:

```bash
python3 scripts/affected_tests.py origin/master   # prints the targets CI would run
```

It maps each changed file to its Bazel label and asks
`rdeps` which tests reach it. So a change under `packages/be_water/` runs
be_water's suite alone, a change under `core/` runs all of them, and a
documentation change runs none.

Two things it cannot see, both falling back to `//...`:

  * **Build files** — `.bzl`, `BUILD.bazel`, `MODULE.bazel` and the lock are
    not targets, so `rdeps` would report a change to the macro every service
    loads as affecting nothing.
  * **CI itself** — editing the workflow or the selector re-runs everything,
    or the decision goes unverified.

## 🧹 GCP Cleanup and Cost Control

### Artifact Registry

  * **Create the Docker repository (first time only):**

    ```bash
    gcloud artifacts repositories create biwenger-docker \
        --repository-format=docker \
        --location=europe-southwest1 \
        --description="Docker images for Biwenger Tools"
    ```

  * **List images in the repository:**

    ```bash
    gcloud artifacts docker images list europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker
    ```

  * **Clean up old images (script):**

    ```bash
    cd scripts/
    ./clean-images-artifact.sh
    ```

    > Keeps the newest digest of each service image and deletes the rest. For
    > the multi-arch `python-base` it keeps the tagged manifest and its
    > per-arch children, and deletes only untagged digests older than
    > `UNTAGGED_MIN_AGE_HOURS` (24 h by default). `DRY_RUN=1` shows what it
    > would delete. Covers both registries: `biwenger-docker` (biwenger-tools)
    > and `be-water-docker` (be-water-app).

  * **Review costs (script):**

    ```bash
    cd scripts/
    ./check-gcp-costs.sh
    ```

    > Audits **both projects** (`biwenger-tools` + `be-water-app`) against the
    > GCP *Free Tier*, plus the billing-account-wide Secret Manager version
    > count. Pass `--project=X` to audit a single project.

    * **Clean local Docker containers:**
    ```
     docker image prune -f
     ```

## ⚠️ Important Notes

  * **Do not commit** `biwenger-tools-sa.json`. It is the one service-account
    key left: the `web` service mounts it from Secret Manager to read Google
    Sheets. Everything else authenticates with ADC or Workload Identity.
  * If a deployment fails, check the **logs in the GCP console** (Cloud Run, Cloud Build, etc.).
  * Make sure you have a `.env` file configured in each module for local development.
