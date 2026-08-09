---
name: openspec-backfill
description: Writes the behaviour spec for code that already exists — point it at a module or package and it derives openspec/specs/{package}/{capability}/spec.md from the source and its tests, then registers the capability in openspec/project.md. Use when a module ships without a spec, or when an audit finds undocumented behaviour.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# Goal

Turn existing code into `openspec/specs/{package}/{capability}/spec.md`.

**Derive, do not invent, and do not interview.** Everything in the output must
trace to source or tests already in the repo. If the code is genuinely
ambiguous, report the ambiguity instead of writing a Requirement that blesses
it — a spec is a promise, and a guessed promise is the one that gets broken
silently.

# Step 0 — Load the house style

Read `CLAUDE.md` § "Specs (`openspec/`)", `openspec/project.md`, and two
existing specs (`openspec/specs/core/http-retry/spec.md` is the short one,
`openspec/specs/biwenger_tools/auto-pick-lineup/spec.md` the full-fat one).
Match them; do not invent a second format.

# Step 1 — Find the capabilities

Read the module and its tests end to end before writing a line.

A capability is **a behaviour someone would ask for by name**, not a file. The
mapping is deliberately not one-to-one:

- **One module, several capabilities** — split when two groups of requirements
  share no motive and could be deleted independently of each other. A logic
  package exposing bidding, an inbox and a digest is three specs, because
  killing one leaves the others untouched.
- **Several modules, one capability** — merge when the modules only make sense
  as one outcome (a scheduled chain: fetch → decide → notify). The spec follows
  the outcome; `Source:` then lists every file.
- **Neither** — plumbing with no observable behaviour of its own (a config
  loader, a dataclass) gets no spec. It shows up inside the requirements of
  whatever uses it.

Name the capability in kebab-case for what it *does* (`auto-pick-lineup`,
`catalog-sync`), never for the file it lives in.

Do not create the capability directory until you have the `spec.md` to put in
it: `check_specs.py` **fails** on a capability directory with no spec.

# Step 2 — Write the Requirements

One `### Requirement:` per rule the code enforces. Each has SHALL wording and a
paragraph of **motive**.

```markdown
### Requirement: <what must be true, as a claim>

<Why. The constraint, the upstream limit, or the failure that produced the
rule. A requirement whose reason is missing gets "simplified" away by the next
reader — that is the whole point of the paragraph.>
```

Prefer the reason over the mechanism: *"the vendor returns HTTP 403 for a
captain priced ≥ 3M"* survives a refactor that *"`_pick_captain` filters on
`price`"* does not.

**When the motive is not recoverable from the code**, do not shrug and write
the mechanism. Dig:

```bash
git log --oneline -- <path>
git log -S'<the constant or branch>' --oneline -- <path>
git blame -L <start>,<end> <path>
```

The commit body usually carries the incident. Put the *reason* in the spec —
and no dates, no commit hashes, no "added in this PR". Same rule as
`.claude/CLAUDE.md` § "Code comments — no testaments": provenance belongs in
`git blame`, and a spec dated today reads as expired in a year.

If the dig turns up nothing and the behaviour looks arbitrary, say so in the
report rather than the spec.

# Step 3 — Turn tests into Scenarios

Every test becomes (or joins) a `#### Scenario:` under the Requirement it
proves. Several tests covering one rule belong in one scenario with several
`WHEN`/`THEN` bullets — a scenario per assertion is noise.

The `*Verifies:*` line names **real test function names**, copied from the
source, comma-separated. A test file name is also a valid reference when the
whole file verifies the scenario.

```bash
grep -rn "^def test_" <path/to/tests>
```

# Step 4 — Mark untested behaviour as a GAP

Behaviour with no test gets its Requirement (it is still what the system must
do) and, instead of a scenario, a blockquote:

```markdown
> **GAP — unverified.** <what is untested, and what a test would have to
> assert>. Candidate for the next test-hardening pass.
```

Never fabricate a test name to fill the line. `check_specs.py` *warns* on a
scenario with no verifier and *fails* on a name that does not exist: an
admitted gap is a to-do, a fabricated name is a false claim of coverage, which
is worse than no spec at all.

# Step 5 — Check

```bash
python3 scripts/check_specs.py
```

Fix everything it reports. Broken references are usually a renamed test —
point the spec at whatever replaced it, do not delete the scenario.

# Step 6 — Register the capability

Add the new spec to the table in `openspec/project.md` § "Packages and their
capabilities", on the row for its package and module. A spec no index points at
is a spec the next session will not find, and will rewrite.

# Worked example

The shape to aim for, lifted from `openspec/specs/core/http-retry/spec.md`:

```markdown
# Capability: http-retry

The shared HTTP retry helper every SDK uses to survive transient upstream
failures without retrying unrecoverable ones.

- **Source:** `core/sdk/http.py` (`retry_http_request`)
- **Verified by:** `core/tests/test_http_retry.py`

---

### Requirement: Retry only what can recover

`retry_http_request(fn, label, backoffs)` SHALL return immediately on the first
success, raise immediately on a 4xx (caller error — retrying never helps), and
retry on 5xx or network errors, sleeping per the `backoffs` tuple. Total
attempts SHALL be `1 + len(backoffs)`; when they exhaust, the last error SHALL
be raised.

#### Scenario: success, fail-fast, retry, exhaust
- **WHEN** the call succeeds first try **THEN** it returns, no retry
- **WHEN** it returns 4xx **THEN** it raises immediately (one call)
- **WHEN** 5xx / network errors persist **THEN** it raises after
  `1 + len(backoffs)` attempts
- *Verifies:* `test_returns_immediately_on_first_success`,
  `test_fail_fast_on_4xx_without_retrying`,
  `test_raises_after_exhausted_retries_on_persistent_5xx`
```

Note what it does *not* do: it never names a private helper's control flow, and
the reason for the 4xx branch ("retrying never helps") is in the requirement
rather than in a comment nobody reads.

# Rules

- Derive from source and tests. Ask the user nothing; report ambiguity instead.
- Never restate the implementation line by line — a spec that mirrors the code
  is a second copy to keep in sync, which is the thing specs exist to avoid.
- No dates, no commit hashes, no session narrative in spec prose.
- One capability per directory, `spec.md` created with the directory.
- `python3 scripts/check_specs.py` must pass before you report.
- Do not touch `openspec/changes/` — that is `openspec-propose`'s ground.
