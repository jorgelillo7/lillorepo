---
name: add-python-dep
description: Adds a new Python dependency to the monorepo, keeping all five dependency layers in sync (module requirements.txt, requirements.in, requirements_lock.txt, BUILD.bazel, and Dockerfile.base). Also rebuilds and pushes the python-base Docker image and updates MODULE.bazel.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Goal

Add a new Python library to the monorepo so it works in Bazel tests, local runs, and the Docker image. All five layers must be in sync — missing any one causes silent failures at runtime (as happened with `python-json-logger`).

## The five layers

| Layer | File | Updated by |
|---|---|---|
| 1 | `[module]/requirements.txt` | You (human intent) |
| 2 | `requirements.in` | Concatenation script |
| 3 | `requirements_lock.txt` | `pip-compile` |
| 4 | `[module]/BUILD.bazel` | Bazel dep declaration |
| 5 | `docker/Dockerfile.base` | Docker image rebuild |

---

# Step 1 — Gather info

Use `AskUserQuestion` to ask (all in one message):

- **Library name** as it appears on PyPI (e.g. `python-json-logger`)
- **Which module needs it**: `core`, `web`, `scraper_job`, or `teams_analyzer`
- **Which BUILD.bazel target** within that module should declare it (e.g. `_init`, `gcp`, `web_lib`)

If the user is unsure about the BUILD.bazel target, read the relevant `BUILD.bazel` and suggest the most specific target that makes sense based on which source file will use the library.

---

# Step 2 — Read current state

Read these files before making any changes:

- `[module]/requirements.txt` — check the library isn't already there
- `requirements.in` — check it isn't already present
- `requirements_lock.txt` — check if it's already pinned (and if so, extract the version)
- `[module]/BUILD.bazel` — find the target where the dep will be added
- `docker/Dockerfile.base` — check if it's already in the pip install list

If the library is already in `requirements_lock.txt`, **do not run pip-compile** — just use the pinned version that's already there and proceed to the layers that are missing it.

---

# Step 3 — Add to module requirements.txt

Edit `[module]/requirements.txt` and append the library name (without version — pip-compile will pin it).

```
# example: adding python-json-logger to core/requirements.txt
python-json-logger
```

Skip this step if already present.

---

# Step 4 — Regenerate requirements.in

Run this exact command from the project root. It must list **all four** module requirements files:

```bash
{
  for req_file in core/requirements.txt \
    packages/biwenger_tools/scraper_job/requirements.txt \
    packages/biwenger_tools/teams_analyzer/requirements.txt \
    packages/biwenger_tools/web/requirements.txt; do
    echo; echo "# From: $req_file"; cat "$req_file"
  done
} > requirements.in
```

Skip this step if the library is already in `requirements.in`.

---

# Step 5 — Regenerate the lock file

Only run this if the library is NOT already in `requirements_lock.txt`.

Check that `pip-compile` is available:

```bash
which pip-compile || pip install pip-tools
```

Then regenerate:

```bash
pip-compile requirements.in -o requirements_lock.txt
```

After it finishes, grep the new `requirements_lock.txt` to extract the exact pinned version:

```bash
grep "^<library-name>" requirements_lock.txt
```

Note: the library name in the lock file uses hyphens (e.g. `python-json-logger==4.1.0`). Save this version — you'll need it for Dockerfile.base.

---

# Step 6 — Add to BUILD.bazel

Edit the target in `[module]/BUILD.bazel` and add the Bazel dep name to its `deps` list.

**PyPI name → Bazel name rule:** replace all hyphens with underscores.
Examples: `python-json-logger` → `python_json_logger`, `google-api-python-client` → `google_api_python_client`

```python
# example
deps = [
    "@pypi//python_json_logger",   # ← add this
    "@pypi//requests",
],
```

Skip this step if already present.

---

# Step 7 — Add to Dockerfile.base

Edit `docker/Dockerfile.base` and add the library with its **exact pinned version** from `requirements_lock.txt` to the `pip install` list. Keep the list alphabetically sorted.

```dockerfile
# example: insert python-json-logger==4.1.0 in alphabetical order
    python-dateutil==2.9.0.post0 \
    python-dotenv==1.1.1 \
    python-json-logger==4.1.0 \   # ← add this
    pytz==2025.2 \
```

Skip this step if already present.

---

# Step 8 — Rebuild and push the python-base image

This step rebuilds the Docker base image for both platforms and pushes it to the registry.

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -f docker/Dockerfile.base \
  -t europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest \
  --push .
```

**If docker buildx is not configured**, run first:
```bash
docker buildx create --name mi_builder --driver docker-container --use
```

After the push completes, extract the new multi-arch digest from the output. Look for a line like:
```
pushing manifest for .../python-base:latest@sha256:XXXXXXX
```

Save that `sha256:XXXXXXX` value.

---

# Step 9 — Update MODULE.bazel digest

Edit `MODULE.bazel` and replace the old digest with the new one:

```python
oci.pull(
    name = "python_with_deps",
    image = "europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base",
    digest = "sha256:NUEVO_DIGEST",   # ← update this
    platforms = [
        "linux/amd64",
        "linux/arm64",
    ],
)
```

Then run:

```bash
bazel mod tidy
```

---

# Step 10 — Verify

Run a quick sanity check:

```bash
bazel build //...
```

If successful, optionally also verify the Docker image:

```bash
bazel run //packages/biwenger_tools/web:load_image_to_docker_local
docker run --rm --entrypoint python3 bazel/web:local -c "import <library>; print('OK')"
```

Replace `<library>` with the importable Python name of the library (e.g. `pythonjsonlogger` for `python-json-logger`).

---

# Step 11 — Report

Tell the user:
- Which layers were updated (and which were already in sync)
- The new docker image digest in MODULE.bazel
- The pinned version added to Dockerfile.base
- Any layers that were skipped and why
