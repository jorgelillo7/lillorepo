# Executing the upgrades check-deps recommends

`check-deps` itself stays read-only. This is the procedure for the day the
owner says "go ahead", written from a full run (cryptography, soupsieve,
Python 3.13 → 3.14, the Google stack, every runtime and dev patch, two Bazel
rules: nine PRs, all shipped without an incident). Read it before starting;
most of it exists because the obvious way went wrong once.

## 1. Measure before touching anything

- **Compute the whole upgrade into a scratch file first**, never into the
  repo, and diff it against the lock:
  `venv/bin/pip-compile --upgrade requirements.in -o /tmp/lock.full`.
  The real list is always longer than the report: transitive patches appear,
  and **new packages** can appear (`google-api-core` started pulling
  `opentelemetry-api`).
- **Classify each change as runtime or dev** by whether it is pinned in
  `docker/Dockerfile.base`. Runtime changes need a `python-base` rebuild; dev
  changes do not.
- **Check vulnerabilities against OSV**, no install needed:
  `POST https://api.osv.dev/v1/querybatch` with every `name==version` from the
  lock. Re-run it at the end to prove the result.
- **A Python minor bump** needs every compiled dependency to ship wheels for
  it at the current pins. Check PyPI's JSON (`/pypi/<name>/<version>/json`)
  for `cp3XX`/`abi3` wheels on manylinux x86_64 (CI, image) and macOS arm64
  (local tests). If all are there, the migration changes no library.
- **Support dates:** `https://endoflife.date/api/python.json`. Bugfix support
  ending is the trigger for a minor bump, not the release of the next one.

## 2. Split into pull requests

One bump per PR is the rule (LP-4), bent where it would be absurd:

| PR | Why alone |
|---|---|
| Each security fix | Reversible without losing anything else |
| A coupled family (google-*, grpcio*, protobuf, proto-plus) | Their pins move together; splitting means partial rebuilds |
| Remaining runtime patches | One rebuild for many harmless bumps |
| Dev tooling (flake8, pyflakes…) | No image, no deploy |
| A Python minor | The biggest blast radius; nothing else in it |
| Each Bazel rule (`rules_python`, `rules_pkg`) | Build-only, no image |

**Upgrade one package without moving the rest** with
`--upgrade-package <name>` (repeat the flag per package). A plain `--upgrade`
belongs only to the last PR, when everything else has shipped. At that point it
should change nothing but the dev tools.

**Order the image PRs:** security fixes first, then the Python minor, then the
families. Each one rebases on the previous one.

## 3. The lock

- Run `pip-compile` on the **same Python minor the lock targets** (its header
  says which). Markers resolve per interpreter: on 3.14 `icalendar` drops
  `typing-extensions`.
- Use `pip-tools==7.6.1` with `CUSTOM_COMPILE_COMMAND` (the exact command is in
  `docs/operations.md`): it fixes the header line 7.6.x would otherwise fill
  with a spurious `--no-index`. 7.5.3 crashes on Python 3.14's pip.
- **Never silence `pip-compile`** (`2>/dev/null`). A crashed run writes
  nothing, and "the lock did not change" then reads as success — which is how
  a broken 7.5.3 once passed for a byte-for-byte reproduction. Check the exit
  code and that the file was rewritten.
- `scripts/check_base_sync.py` compares the lock with `Dockerfile.base`. A new
  transitive runtime dependency fails it until it is added to the Dockerfile,
  in alphabetical order.
- After a rebase, regenerate `MODULE.bazel.lock` rather than trusting a
  textual merge: `bazel mod deps --lockfile_mode=update`, then
  `bazel build //... --lockfile_mode=error`.
- `bazel mod tidy` reorders attributes. When two PRs touch `MODULE.bazel` in
  parallel, keep only the version line in each, or they conflict for nothing.

## 4. The python-base image: never push it as `latest` early

- **Push each candidate under its own tag** (`:cryptography-50`,
  `:python-3.14`), never `:latest`. Moving `latest` untags the image `master`
  still pins. The CI cleanup deletes untagged digests older than 24 h after
  every deploy, so the next deploy can no longer pull its base.
- **Move `latest` only after the merge**, and give the previous image a tag
  (`pre-<change>`) so a revert still has something to pull.
- Remove the temporary tags a few days later. The cleanup job then takes the
  rest.
- **zsh trap:** `"$IMG:cryptography"` is read as a `:c` modifier and pushes to a
  repository called `python-baseryptography-50`. Always write `"${IMG}:tag"`.
- A draft PR is fine while there is no Docker. Say in it that it must not
  merge: Bazel tests the new lock, but production runs whatever the image has.

## 5. Verify the image, not just the tests

Tests mock Firestore and never boot gunicorn. Before merging an image PR:

1. **Inside the image** (`docker run --platform linux/amd64 --entrypoint
   python3`), check the Python and library versions and import the whole
   stack. On a Mac this is emulated: fine for imports, too slow for
   rendering (matplotlib's `savefig` stalls) — prove that natively with a
   throwaway Cloud Build step, which runs as the compute account and so needs
   `artifactregistry.reader` + `logging.logWriter` granted just for it.
2. **Talk to the real services from it**: mount your ADC
   (`-v ~/.config/gcloud/application_default_credentials.json:/adc.json:ro
   -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json`) and read a known Firestore
   document. Reads only.
3. **Boot the real containers**: pin the new digest, then
   `bazel run //packages/<pkg>/<module>:load_image_to_docker_local`, and curl
   the pages that exercise the bumped library (matplotlib → a digest-style
   PNG, icalendar → `/calendario`).
4. **Build every production image** for amd64:
   `bazel build --platforms=//platforms:linux_amd64 $(bazel query
   "kind(oci_image, //packages/...)" | grep _gcp)`.
5. **When a changelog is empty, compare outputs.** For `rules_pkg` the 15
   `pkg_tar` layers were hashed before and after; they were byte-identical.

Checks that lied and had to be redone:

- **Counting `.pyc` after importing** counts the ones the import itself just
  wrote. Count them in a fresh container, before importing anything.
- **Grepping `bazel-testlogs/` for warnings** finds stale logs from old runs.
  Restrict it to `-newer <file you edited>`.
- **Guessing a URL** (`/26-27/palmares`, `/26-27/calendario`) gave 404s that
  looked like regressions. Take routes from `@bp.route`.

## 6. Ship one at a time

For each PR: head check, green checks, merge, `gh run watch` on the
**`deploy.yml`** run for the merge commit (`gh run list --workflow deploy.yml`
— GitHub's "Dependency Graph" workflow also runs on every push and, watched by
mistake, reports success after one job), services
`True`, pages at 200, then **application errors since the deploy**. Only then
merge the next one, so a failure has one suspect.

- **Search application errors with `severity>=ERROR`**, which the logger
  writes (`structured-logging` spec). Before that fix every entry landed as
  `DEFAULT`, so the filter was blind to them. Expect the known
  `run.services.setIamPolicy` audit denials from CI's
  `--allow-unauthenticated` on every deploy; they are not regressions.
- **A lock-only or dev-only change deploys nothing.** `deploy.yml` reacts to
  `MODULE.bazel` and to code, not to `requirements_lock.txt`. Do not wait for
  a run that is never coming.
- **`rules_python` decides the toolchain patch.** Its `python/versions.bzl`
  at the release tag lists what it can resolve. The image can be ahead (it
  was on 3.14.7 against Bazel's 3.14.4) until a release maps the newer patch.

## 7. The owner's machine

`python3` on the Mac should be the same minor as the image. Use the official
python.org installer: it keeps global `pip3` working, whereas Homebrew's Python
blocks it (PEP 668). Verify the installer before opening it:
`pkgutil --check-signature` (Python Software Foundation, notarised) and
`spctl --assess --type install`. Then:

- run `Install Certificates.command`;
- put the new version first in the PATH in `.zshrc`, and keep the old one
  behind it for its global tools (frida);
- rebuild `venv/` with `pip-tools==7.6.1`;
- prove it on an unchanged `requirements.in`: the lock must come out byte for
  byte identical **and** freshly written (compare timestamps, not just
  content — a crashed run leaves identical content too).
