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

  * **Python 3.x**
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

  pytest core/tests/
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
  /tmp/mutenv/bin/pip install pytest requests-mock freezegun requests unidecode \
    google-cloud-firestore google-auth google-api-python-client python-dateutil \
    python-json-logger python-dotenv Flask matplotlib 'mutmut<3'

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

The project uses a three-level system to manage dependencies, keeping modules isolated and guaranteeing 100% reproducible builds.

1.  **`[module]/requirements.txt`** (e.g. `core/requirements.txt`): The **starting point and source of truth**. This is where you, as a developer, add or remove the libraries a specific module needs.
2.  **`requirements.in`**: An **intermediate, auto-generated file**. It consolidates the lists from all modules into a single place for the next tool. **Never edit this file by hand.**
3.  **`requirements_lock.txt`**: The **final, locked file** generated by the computer. It contains the exact list of all libraries (direct and indirect) with their versions and hashes — what Bazel uses. **Never edit this file by hand.**

> The `add-python-dep` skill automates this whole flow (including the
> `python-base` image rebuild). The manual steps below document what it does.

The workflow for adding a new library (using `numpy` in the `core` module as an example):

### Step 1: Add the library to the module's `requirements.txt`

Decide that the `core` module needs `numpy`. Open `core/requirements.txt` and add it.

**File: `core/requirements.txt`**

```diff
requests
google-api-python-client
google-auth-oauthlib
google-auth
python-dateutil
python-json-logger
black
flake8
pytest
requests-mock
+ numpy
```

-----

### Step 2: Regenerate the central `requirements.in`

Run this command from the project root. It will pick up the changes you made in `core/requirements.txt` and update the central file.

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

-----

### Step 3: Regenerate the Lock File

This command reads the `requirements.in` you just generated and resolves all dependencies, creating the final `requirements_lock.txt`.

*(Remember to have `pip-tools` installed: `pip install pip-tools`)*

```bash
pip-compile requirements.in -o requirements_lock.txt
```

-----

### Step 4: Use the new library in `BUILD.bazel`

Now that the library is available to Bazel, go to `core/BUILD.bazel` and add it to the `deps` list of the **most specific sub-target** that needs it.

`core/BUILD.bazel` exposes granular targets — use the right one to avoid bloating other packages:

| Target | When to add here |
|---|---|
| `//core:gcp` | Library used by `sdk/gcp.py` or `utils.py` |
| `//core:telegram` | Library used by `sdk/telegram.py` |
| `//core:biwenger` | Library used by `sdk/biwenger.py` |
| `//core` (umbrella) | Shared by all of the above |

Remember that Bazel converts hyphens (-) to underscores (_). For numpy, the name is the same.

**File: `core/BUILD.bazel`** (example: adding `numpy` to the `gcp` target)

```python
py_library(
    name = "gcp",
    srcs = ["sdk/gcp.py", "utils.py"],
    deps = [
        ":_init",
        "@pypi//google_api_python_client",
        # ... (other dependencies)
        # Add the new dependency
        "@pypi//numpy",
    ],
    visibility = ["//visibility:public"],
)
```

-----

### Step 5: Verify with Bazel

Finally, run a Bazel command to confirm everything works.

  ```bash
  bazel build //...

  ```

If the command completes successfully, you have added the dependency in a clean, isolated, and reproducible way.

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

### Updating a secret (e.g. token.json):
```bash
gcloud secrets versions add token_json --data-file="token.json"
```

## 💅 Linter and Auto-formatter

Flake8 (linter) and Black (formatter) run **on every push to `master`** as
the `lint` job in `.github/workflows/deploy.yml`. A lint failure blocks
`test` and the deploy.

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

    > This script deletes all old images, keeping only the one tagged `latest`.
    > Covers both registries: `biwenger-docker` (biwenger-tools) and
    > `be-water-docker` (be-water-app).

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

  * **Do not commit** the credentials file `biwenger-tools-sa.json`.
  * If a deployment fails, check the **logs in the GCP console** (Cloud Run, Cloud Build, etc.).
  * Make sure you have a `.env` file configured in each module for local development.
