# Google Agent Skills

This repo curates a subset of skills from the official **Google Agent Skills** repository:

- **Upstream:** <https://github.com/google/skills>
- **Org:** `google` (official)
- **License:** Apache 2.0
- **Format:** each skill is a folder with a `SKILL.md` (YAML frontmatter + markdown body) and optional `references/` files. Same shape Claude Code already understands.

The selected skills live under `.claude/skills/google-*/` and are committed to the repo so they are available to anyone who clones it.

## Why a local sync script instead of `npx skills add`

The official install command is:

```bash
npx skills add google/skills
```

That command delegates to `skills.sh` / `agentskills.io` — a third-party aggregator that is not Google. It runs arbitrary JS on your machine to copy what is essentially a handful of Markdown files. We avoid that layer entirely.

Our script (`scripts/sync-google-skills.sh`) only trusts:

- `git`
- `https://github.com/google/skills.git` (official Google org)

…and copies the selected `SKILL.md` files into the repo with diff + confirmation before any overwrite.

## Usage

```bash
# What's available upstream
./scripts/sync-google-skills.sh list

# Install or update one or more skills
./scripts/sync-google-skills.sh add cloud-run-basics firebase-basics

# Check for upstream changes on every installed Google skill (run periodically)
./scripts/sync-google-skills.sh sync

# Remove
./scripts/sync-google-skills.sh remove cloud-run-basics
```

Every overwrite is gated by an interactive `[y/N]` after showing the file-level diff. The script never touches skills that don't start with the `google-` prefix.

## What's installed in this repo

| Skill | Why it's relevant for lillorepo |
|---|---|
| `google-cloud-run-basics` | Every service (web, api, bot, chucknorris_bot) and job (scraper) is Cloud Run |
| `google-cloud-recipe-auth` | We use ADC, Service Account keys, Secret Manager — this skill captures the canonical patterns |
| `google-cloud-waf-security` | Security pillar of the Well-Architected Framework — IAM, network, data protection, ops |
| `google-cloud-waf-reliability` | Reliability pillar — useful for the Cloud Run + Cloud Run Jobs setup |
| `google-cloud-waf-cost-optimization` | Cost pillar — we run on the free tier and care about Artifact Registry cleanup |
| `google-firebase-basics` | Firestore is now the system of record (shipped 2026-05-21; see `docs/firestore.md` for schemas/indexes) |

Skills explicitly not installed (and why): `alloydb-basics`, `bigquery-basics`, `cloud-sql-basics`, `gke-basics` (we don't use any of those Google products), `gemini-api` (this repo uses Claude / Anthropic), `google-cloud-networking-observability` (overkill for our footprint), `google-cloud-recipe-onboarding` (project already created).

## Refresh cadence

There's no automation. When you remember (or after a few weeks pass), run:

```bash
./scripts/sync-google-skills.sh sync
```

It will list each installed skill as `up to date` or show a diff and prompt you per change.
