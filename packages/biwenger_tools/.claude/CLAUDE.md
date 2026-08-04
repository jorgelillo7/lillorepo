# biwenger_tools — Claude Notes

Skills specific to this package. They assume the Lloros League: its reglamento,
its scoring, its seven managers. Nothing here is reusable in another package,
which is exactly why it does not live at the repo root.

Read `/CLAUDE.md` and `/.claude/CLAUDE.md` first — the repo-wide rules and the
generic skills apply here too. Directory-scoped skills win over a root skill of
the same name when the files you are working on live under this package.

## Skills

| Skill | When |
|---|---|
| [`draft`](skills/draft/SKILL.md) | Once a year, at the pre-season draft: build the 15-man squad from the frozen market CSV. |
| [`season-rollover`](skills/season-rollover/SKILL.md) | Once a year, when the season ends: roll the code over to the new season and open the PR. |

Both run **once a year and days apart**, so neither is in your muscle memory
when you need it. Read its `SKILL.md` in full before starting — that is the
point of them existing.

## Two directories called `draft`, opposite powers

| Path | Reads | Writes |
|---|:-:|:-:|
| `packages/biwenger_tools/.claude/skills/draft/scripts/` | ✅ | ❌ nothing, ever |
| `/packages/biwenger_tools/scripts/draft/` | ✅ | ✅ Firestore, the bucket, the group chat |

The skill's scripts only ever produce analysis for you to decide with. The
package's scripts move real state: `open.py` greets the league and starts the
clock, `reset.py` wipes the picks, `backfill_timings.py` rewrites history.

Never reach for one when you mean the other.

## Where the rest lives

- **Behaviour** — `/openspec/specs/biwenger_tools/{capability}/spec.md`
- **Runbook** — [`../OPERATIONS.md`](../OPERATIONS.md)
- **Web design system** — [`../web/DESIGN.md`](../web/DESIGN.md)
- **Shipped changes** — [`../release-notes.md`](../release-notes.md)
