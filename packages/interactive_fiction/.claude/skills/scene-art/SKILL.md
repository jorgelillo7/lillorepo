---
name: scene-art
description: Art for a point-and-click chapter — keep the series' art bible in line with the text, compose image prompts from it, take generated images in, place and check hotspots, validate, publish. Use when a chapter arrives or changes, or a scene needs new or fixed art.
---

# Goal

Every image of a series looks like the same world, and matches what the text
says. The art bible (`stories/<series>/art-bible.json`) holds one description
per character and place, each backed by sentences quoted from the story; the
prompts are composed from it, never typed by hand. Read `README.md` §
"Point-and-click mode" and `OPERATIONS.md` § "Art for point-and-click" first.

Nothing from a story is ever committed: bible, prompts, images, originals and
scene files all live in the gitignored series folder.

# Files

| File (in `stories/<series>/`) | What |
|---|---|
| `art-bible.json` | `style`, `characters`, `locations` (each with `sources` quotes and optional `open` questions for the author), `images` (status, file, location, characters, `editOf`, `scene`, `prompt` used) |
| `NN-scenes.json` | Per chapter: scene id → image, `room`, aspect, hotspots; passage → scene |
| `scenes/*.jpg` | Web-size images (~1600 px wide), published |
| `art-originals/` | Full-size originals and prompt notes, never published |

# Step 1 — Read the chapter before drawing anything

```bash
npm run stories            # validator: the chapter must import cleanly first
npm run explore -- <series>
```

List the chapter's places and characters from the passages themselves: which
passages happen in which room, who is on screen, what the player can click (the
links each passage offers). A passage that only changes what is visible (a door
ajar, someone on the bed) is a variant of a room, not a new room.

# Step 2 — Update the bible

- A new character or place gets an entry whose `description` (English,
  prompt-ready) is backed by `sources`: exact sentences copied from the
  passages. Copy, do not paraphrase — the build checks each quote is still in
  the text.
- A detail the text gives and an image could miss (an accessory, a count —
  "three bars") goes into the description explicitly.
- Anything ambiguous or contradictory goes into `open`, as a question for the
  author. Do not resolve it by guessing.
- New images are `"status": "planned"` with their `location`, `characters`,
  `scene` (the shot: composition, the moment, every clickable object visible
  and separate), and `editOf` when it is the same room changed.

# Step 3 — Prompts

```bash
npm run prompts -- <series>            # every planned image
npm run prompts -- <series> <id> ...   # specific ones
```

Hand them to the owner for the Gemini app (the API's free tier has no image
quota; never use a paid key). One chat per batch so the style holds; an
`editOf` image needs its base uploaded first.

# Step 4 — Take the images in

1. Save originals to `art-originals/<id>.jpg`.
2. Web copy: `sips -Z 1600 -s format jpeg -s formatOptions 78 <original> --out scenes/<id>.jpg`.
3. **Review against the bible before using it.** Crop the details at the
   original's scale and check every fact the description fixes (counts,
   clothes, accessories, what is on the desk). A miss becomes a new planned
   `editOf` image that fixes only that, not a regeneration.
4. In the bible: `status: "generated"`, `file`, and `prompt` (what was pasted).

# Step 5 — Hotspots

- One rectangle per clickable object, `[x, y, w, h]` in percent of the image;
  `targets` are the passages it leads to (first one offered wins).
- Same `room` for every view of one room (no door transition between them).
- Check with an overlay before shipping: render the image with the rectangles
  drawn on it (an HTML page with absolutely positioned outlined boxes,
  screenshotted with headless Chrome) and look at it.

# Step 6 — Validate and play it

```bash
npm run stories    # fails on a scene/bible/quote problem
npm test
npm run build      # drafts left out
```

Play the chapter end to end by clicking hotspots (headless Chrome over CDP, or
by hand on `npm run preview`), and check that a move between rooms plays the door
and a move within one does not.

# Step 7 — Publish and report

Republish the test site, then tell the owner: what changed, every `open`
question for the author, and any image that still misses a fact.

# Rules

- Never type a description into a prompt by hand — change the bible.
- Never paraphrase a quote.
- Never spend money: the Gemini app by hand, not the paid API.
- Nothing from the series folder goes into git.
