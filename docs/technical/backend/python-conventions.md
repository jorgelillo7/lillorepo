# Python in lillorepo — repo conventions

How Python is written **in this monorepo**, distilled from the code already
running in production. This is not a generic guide (see
`python-best-practices.md` for that): every rule here exists because
something in this repo motivated it, and the motive is stated. A rule that
loses its motive gets changed.

Complements (does not repeat) `CLAUDE.md` (workflow, PRs, deps) and
`.claude/CLAUDE.md` (comment policy). Examples cite real files — reading them
is worth more than any paragraph.

---

## 1. Where things live

```
core/sdk/        Clients for external services (Biwenger, JP, Telegram,
                 Firestore, GCP). No business logic: they speak a protocol.
core/domain/     Shared models (dataclasses with to_firestore/from_*).
core/constants.py  League facts read by more than one package. A fact that
                 two packages write separately ends up diverging (it
                 happened to the draft order: "Lucen"/"Lillo" vs
                 "Lucena"/"Jorge").
packages/*/logic/   The module's business logic.
packages/*/app.py   Flat HTTP shell (Flask): parse, delegate, serialise.
packages/*/scripts/ One-off Firestore surgery (see §7).
```

**The layer rule** — the draft is the canon:

| Layer | Example | May touch |
|---|---|---|
| Pure logic | `api/logic/draft.py` | nothing: no HTTP, no Firestore, no Telegram |
| Service | `api/logic/draft_service/` | persistence + clients, orchestrates the pure logic |
| HTTP route | `api/app.py` | request/response and calling the service |
| Bot | `bot/app.py` | **zero business logic**: formats and forwards; the api answers with a ready-to-send `message` |

Pure logic is tested with no mocks; the service with small fakes; the route
only pins the wiring. If a logic test needs `MagicMock`, the layer is cut in
the wrong place.

## 2. Functions and dataclasses before classes

Default: pure functions + `@dataclass` for state (`DraftState`, `Pick`,
`NameMatch`). A class only when there is real session state to hold
(`BiwengerClient` keeps auth + a `requests.Session`). No inheritance between
our own classes; explicit composition.

## 3. Errors: loud beats silent

- **A quiet failure is worse than a crash.** JP answers an invalid token
  with HTTP 200 and `{"error": "auth"}`; that parsed to an empty list and
  the digest would have run with no data. The rule: validate the *payload*,
  not just the status (`core/sdk/jp.py::_raise_if_unhealthy`).
- **Never retry non-idempotent mutations.** `retry_http_request` is for
  reads and for writes that carry an idempotency key. Biwenger's admin
  endpoints (204, empty body, no key) go through a direct POST with a
  comment saying why (`BiwengerClient._post_admin_operation`). A retry there
  charges twice.
- **Verify after writing** when the API answers an empty 204: re-reading
  state is the only confirmation that exists.
- **Idempotency is built on our side**: deterministic document + Firestore
  transaction BEFORE calling the external service
  (`draft_service._reserve_pick`). Telegram retries webhooks; count on it.
- In the bot, every api error reaches the chat through a single helper
  (`_report_api_error`) with `html.escape` — an error message that itself
  fails Telegram's parser leaves the user with no feedback at all.

## 4. Logging

`core.utils.get_logger(__name__)` — JSON to stdout, Cloud Logging indexes
it. Data goes in `extra={...}`, never interpolated into the message: `extra`
is filterable (`jsonPayload.chat_id=...`), the f-string is not. No `print`
outside scripts.

## 5. Docstrings, comments and types

- Full policy in `.claude/CLAUDE.md` ("no testaments"). Summary: the
  docstring states the **contract**; a comment exists only when the *why*
  is non-obvious; no dates, no history, no PR references.
- Type hints on every public signature. Explicit `X | None` when the
  default is `None`. No gratuitous `Any`; no hints on obvious locals.
- User-facing strings in **Spanish**; code, logs and docstrings in English.

## 6. Tests

- Every module has its Bazel target (`//packages/.../x:x_tests`); the whole
  suite is `bazel test //...` and CI requires it green before deploying.
- **Spec and test are a pair** (`openspec/`): a scenario without a test is
  a gap; a test without a scenario is undocumented behaviour.
- Mock **at the boundary**, not inside: an in-memory `FakeFirestore`,
  `MagicMock` for the Biwenger session, `_run_in_background` patched to run
  synchronously. Pure logic is never mocked.
- Every path that moves money has a duplicate-call test: "the second call
  does NOT reach the external service"
  (`test_duplicate_applied_pick_does_not_recall_biwenger`) and "a failing
  POST is issued exactly once" (`call_count == 1`).
- Tests never touch the network. If a config default points at a URL, the
  fixture redirects it to a local file (the path-over-URL precedence of
  `DRAFT_MARKET_CSV_PATH` exists for this).

## 7. Operational scripts

Fixed pattern (`scripts/draft/reset.py`, `fetch_palmares.py`):

They live under `packages/{package}/scripts/{domain}/`, grouped by what
they operate on — `draft/` and `scraper/` in `biwenger_tools`. The
directory carries the subject, so the file name only has to carry the verb.

- **Dry-run by default, `--apply` to write.** No exceptions: the dry run
  shows what it would do, with counts.
- ADC (`gcloud auth application-default login`), never keys in the script.
- Bootstrap with `sys.path.insert(0, ...parents[N])` so it runs from the
  repo root with no installation.
- If it deletes anything: print what it keeps and why (the draft reset
  keeps `managers` and says so).

## 8. Stack traps (learned, not theoretical)

- **`requests.text` with no declared charset decodes as ISO-8859-1** (per
  RFC). A UTF-8 CSV served by GCS without a `content-type` loses every
  accent. Decode explicitly: `response.content.decode("utf-8-sig")`.
- **`source .env` in bash expands `$`**: a token with `$` inside gets
  silently truncated. `.env` files are read from Python, not from the shell.
- **Per-instance caches on Cloud Run**: fine for frozen data (the draft
  market), but re-uploading the object does NOT refresh warm instances;
  document it wherever it is operated.
- **`--set-env-vars` replaces the whole block** on deploy: an env var that
  must survive lives in a GitHub repository variable, not hand-set on
  Cloud Run.
- **Telegram ids**: a chat with a negative id is a group; user ids are
  always positive. Never derive one from the other.

## 9. Dependencies

Never added by hand: the `add-python-dep` skill keeps the five layers in
sync. Never mix a dependency bump into a feature PR (`CLAUDE.md` rule).
When in doubt: can it be done with `requests` and the stdlib? — the draft
reads GCS with `requests` precisely to avoid pulling in
`google-cloud-storage`.
