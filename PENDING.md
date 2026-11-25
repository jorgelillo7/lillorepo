# Pending work

The index of what is still open. **One line per item.** If it needs more than
that, the reasoning lives where it belongs and this file links to it:

- behaviour and decisions → `openspec/`
- technical evaluations and parked work → `docs/technical/parked-work.md`
- anything else → the PR that closed it, and `git log`

What each `biwenger_tools` measurement asks, what it has found and what would
change the code: [`docs/technical/backend/measurements.md`](docs/technical/backend/measurements.md).

Never deleted; lines are pruned as items ship. Grouped by area. Parked infra and `core` work lives only in
[`docs/technical/parked-work.md`](docs/technical/parked-work.md). What has **shipped** lives in
`packages/biwenger_tools/release-notes.md`, and the current state of the repo
in `STATUS.md` — neither belongs here.

**👤 needs you** · **⏳ waiting on a trigger or on data** · **🔨 ready to pick up** ·
**🚧 blocked on you, and parked by your call** — not up for planning until you unblock it

---

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Monthly review of the open measurements (squad floor, absence sales, captain upgrade, Oráculo blend, squad composition, captain by win chance, defenders against Barcelona or Madrid) — **next: late December** | The questions, their data so far and how to read each: [measurements.md § Monthly review](docs/technical/backend/measurements.md#monthly-review) |
| ⏳ | Should the starts penalty be the draft's default? | Next pre-season, with both fifteens side by side · `--starts-penalty` exists and is off; on the Aspas case it drops him from 1st to 3rd (143 → 75) |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Photos: **(1)** copy, never move, the ten-year-old disk onto the 5 TB one and verify it — urgent, no code; **(2)** iCloud to 2 TB, Camera sharing to the Shared Library, Google Photos backup on both phones, messaging auto-save rules; **(3)** a trial session of the Claude Code + `osxphotos` album agent on one month, answering the plan's open questions; **(4)** then the skill and the import of the old disk as albums | You for 1 and 2 · the plan and its open questions are in `packages/my_photos/README.md` |

## interactive_fiction

Next session starts here; the story-specific detail is in the local plan (`.claude/plans/interactive-fiction.md`, gitignored).

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Chapter 3 into the reader: art, scenes, SCARE among its valid codes, the condition/inventory setup | The author finishing it in `Capitulo 3/fuente/` on his `master` |
| 👤 | On a phone, share a chapter over WhatsApp and check its card (title, image, description) | You |
| 🔨 | 3D menu for the reader, then take it and [the 3D draft](https://interactive-fiction-draft3d.jorgelillo.workers.dev) to the author: the author's validation decides whether the 3D continues (more rooms, full quality, then into the reader) | You and the author · [evaluation](docs/technical/parked-work.md#interactive_fiction--a-3d-draft-of-chapter-1) |
| 🚧 | Android app: wrap the site as a Trusted Web Activity (Bubblewrap; Google Play account US$25 once, content rating for horror/violence) — reuses the web as is | The 3D reader on the main URL (`openspec/changes/interactive-fiction-3d-reader`) |
| 🚧 | A custom domain and a save export code | Before the Android app or any promotion: saves live in the browser per origin, so a new URL loses them |

## wishlist

| | What is missing | Waiting on |
|---|---|---|
| 👤 | After the next deploy, add a gift from an iPhone with each photo button (camera and library) and check both photos show. They are now `<button>`s opening a hidden file input; the first upload, through the old labels, is stored and served clean | You · the browser side has no automated test |
| 🔨 | Birthdays on the same list instead of one list per event: an admin "Ocasión" panel to edit the title and subtitle, pick a theme (colours and header icon) and hide a recipient, plus a "new occasion" action that releases unbought reservations and hides bought gifts; unbought gifts carry over by themselves. Limit: one occasion at a time | **Before 24/03** (first birthday after Christmas) · supersedes [`openspec/changes/wishlist-events/`](openspec/changes/wishlist-events/proposal.md), which gets rewritten to this |
| 👤 | Filter the gifts on the list page | You: what to filter by (recipient, price, bought or not…) |
| 🔨 | Web: `srcset` with WebP photos (needs the photo stored at more than one size, from the admin page's canvas and for the seed) | Ready · [web review](docs/technical/web-guidance.md#review-of-2026-11) |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Activate Google Sign-In | ~10 min of Console clicks · **the studio photo is off for everyone until this is done** (it follows the Google-verified admin) · the ficha editor is built, tested and deployed behind a 404 until this is done · runbook in `packages/be_water/OPERATIONS.md` · **no code change needed**: be_water's CSP already allows Google Sign-In's script, style and frames (#542) |
| 🔨 | `style-src 'unsafe-inline'` out of both CSPs: move the templates' `style` attributes and `<style>` blocks into CSS. Tailwind is compiled at build time in both webs and Biwenger follows the system's dark mode | Ready · [web review](docs/technical/web-guidance.md#review-of-2026-11) item 8 |
