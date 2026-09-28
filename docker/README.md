# `python-base` Docker image

Pre-built base used by every service image. Built once and reused via the
digest pinned in `MODULE.bazel`. The dependency list in `Dockerfile.base`
must stay in sync with `requirements_lock.txt` — when the lockfile changes,
rebuild and re-pin.

## Rebuild & push (linux/amd64 only)

```bash
# One-time builder setup
docker buildx create --name mi_builder --driver docker-container --use

# Auth to Artifact Registry (one-time per machine)
gcloud auth configure-docker europe-southwest1-docker.pkg.dev

# amd64 only: Cloud Run is amd64, and a second architecture doubled the
# registry for the one use a Mac had for it (see docs/gcp.md).
docker buildx build \
  --platform linux/amd64 \
  -f docker/Dockerfile.base \
  -t europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest \
  --push .
```

After the push, grab the new digest and update `MODULE.bazel`:

```bash
gcloud artifacts docker images list \
  europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base \
  --include-tags --filter='tags:latest' \
  --format='value(version)' | head -1
```

Then in `MODULE.bazel`, replace the `digest = "sha256:..."` of the
`oci.pull(name = "python_with_deps", ...)` block with the new value.

## Local-only build (single arch, no push)

Only useful if you want to inspect the image without pushing:

```bash
docker build -f docker/Dockerfile.base -t bazel/python-base-all:latest .
```