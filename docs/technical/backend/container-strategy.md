# Container strategy

How this repo builds the images Cloud Run runs, and why it is built that way.
Read this before proposing a change to `docker/Dockerfile.base`,
`tools/bazel/python_service.bzl` or the base image pin.

---

## What we build

A service image is **one shared fat base plus two thin source layers**:

```
python-base (python:3.13-slim + every runtime dep pre-installed, pinned by digest)
  └── core_layer      — the shared library, as a tar of .py files
  └── code_layer      — the module's own .py, templates/, static/, entrypoint.sh
```

There is **no `py_binary` inside the image**. Bazel is the build system and the
test runner, but the container runs the base image's own CPython over plain
sources, found through `PYTHONPATH=/app`. `entrypoint.sh` — an actual `sh`
script — unpacks `core_srcs.tar` and execs the app.

Consequences worth knowing before you change anything:

- **The image layers are architecture-independent.** They are `.py` text files.
  What makes an image amd64 or arm64 is only which variant of the multi-arch
  base `oci_image` selects, which is why every push passes
  `--platforms=//platforms:linux_amd64`. Forget that flag on an ARM Mac and you
  push an arm64 image that Cloud Run cannot run.
- **Only `templates/**` and `static/**` are shipped as data.** The
  `python_service` macro globs exactly those two, plus `**/*.py`. A `.csv`,
  `.json` or `.sql` a service reads at runtime will not be in the image, and the
  service will start fine and fail on the request that needs it. This is why
  `DRAFT_MARKET_CSV_URL` reads from a bucket instead of a bundled file.
- **The base is pinned by digest, never by tag** (`MODULE.bazel`,
  `oci.pull(name = "python_with_deps")`). Rebuild instructions live in
  `docker/README.md`; the `add-python-dep` skill walks the whole five-layer flow.

## The two dependency universes

Bazel resolves `requirements_lock.txt` for tests and local runs. Production runs
whatever `docker/Dockerfile.base` pip-installs. **These are different files kept
in step by hand**, and drift between them ships as green tests plus an
`ImportError` at cold start.

`scripts/check_base_sync.py` guards it in the `Lint` job: every runtime package
in the lock must be installed in the image at the same version. Dev tools
(`pytest`, `black`, `flake8`, `requests-mock`, `freezegun`) are deliberately
absent from the image — dead weight in Cloud Run — and are marked as such under
the `# dev-only` line in `core/requirements.txt`.

## Why not distroless

Evaluated 2026-08-07. **Decision: stay on `python:3.13-slim`.**

Measured against the public registries:

| Base | Compressed | Layers |
|---|---|---|
| `python:3.13-slim` (ours) | 41.0 MB | 4 |
| `distroless/python3-debian13` | 21.4 MB | 48 |

The saving is ~20 MB. The registry holds 159 MB of a 512 MB free tier, and the
bulk of every image is matplotlib, numpy, grpcio and google-cloud — identical
either way. So the saving does not buy headroom that is under pressure.

The cost is not small:

- **Distroless ships no pip.** Our whole model is "pip install into the base", so
  `Dockerfile.base` would become a multi-stage build copying `site-packages`.
- **No shell.** Every `entrypoint.sh` dies, and `core` needs another route to
  `/app` — a redesign across all five services.
- **Native wheels need revalidating** (matplotlib, pillow, grpcio, cryptography)
  against a base without the Debian userland.

And the argument that usually wins for distroless barely applies here:
**Cloud Run has no `exec`.** There is no shell session to reach, for us or for
anyone else, so removing `sh` defends against an attacker who already has RCE in
the Flask app — and even then only removes convenience.

Distroless answers a Kubernetes-shaped problem: shared node surface, `kubectl
exec` as a real attack path, a platform team maintaining a base image. None of
those describe a single-user Cloud Run side project.

**What would reopen this:** cold start starting to eat the 09:00 digest SLO (it
sits at ~5–10 s against a 5 min budget), or free-tier pressure in Artifact
Registry.

## Related

- [`python-conventions.md`](python-conventions.md) — layer rules and failure policy
- [`../../operations.md`](../../operations.md) — dependency workflow, cleanup, costs
- [`../../../docker/README.md`](../../../docker/README.md) — rebuilding and re-pinning the base
