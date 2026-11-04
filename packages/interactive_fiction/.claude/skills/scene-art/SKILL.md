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

# Step 3 — Generate

Every call is paid (the API has no free tier for images), so confirm the
spend with the owner first, and dry-run:

```bash
npm run art -- <series> --dry-run      # the requests and their estimated cost
npm run art -- <series>                # every planned image (--max N caps the run)
npm run art -- <series> <id> --note "…"   # one image again, with a correction
```

`GEMINI_API_KEY` must hold a paid key, exported for the shell only — see
OPERATIONS, "Art for point-and-click". New images get the bible's
`styleReference`, and each character's `reference` (the author's concept art);
an edit gets the full-size original of the image it changes.

Without a key: `npm run prompts -- <series>` prints the same prompts for the
owner to paste in the Gemini app; an `editOf` image needs its base uploaded.

# Step 4 — Review the images

`npm run art` has already saved the original, the web copy and the prompt.
(Images made in the app by hand: original to `art-originals/<id>.jpg`, web copy
with `sips -Z 1600 -s format jpeg -s formatOptions 78 <original> --out scenes/<id>.jpg`,
then `status`, `file` and `prompt` in the bible.)

1. **Review against the bible before using it.** Crop the details at the
   original's scale and check every fact the description fixes (counts,
   clothes, accessories, what is on the desk). A miss becomes a new planned
   `editOf` image that fixes only that, not a regeneration of the room.
2. Watch for additions nobody asked for: the model sometimes adds a close-up
   or a second copy of a detail it was told to change. `--note` says what it
   must not add.

# Step 5 — Hotspots

Start from a draft: list each image's passages in the bible
(`"passages": { "02": ["Inicio", …] }`), then

```bash
npm run scenes:draft -- <series> <chapter>   # writes <chapter>-scenes.json
```

It has one scene per image and one hotspot per linked passage, labelled with
the story's own link text, each with no area yet — the build refuses the file
until every hotspot is placed. Wire it into `series.json` only once the
images are in. A passage whose picture depends on the state (the same passage
showing two moments) can have one scene only: pick the common one.

- One rectangle per clickable object, `[x, y, w, h]` in percent of the image;
  `targets` are the passages it leads to.
- **Several choices, one object — the standard:** when choices go through the
  same thing in the picture (the three exits of a door, the two corridors at
  the top of a stair, the answers given to a character), give that object
  **one** hotspot listing all their targets. A passage that offers one of them
  makes it a plain click; one that offers several opens a menu beside the
  object. Merge the draft's hotspots that way; leave a choice as a text button
  only when nothing in the picture stands for it.
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

```bash
npm run play       # each chapter's shortest path to an ending, clicked in headless Chrome
```

It clicks hotspots and links by their choice label, so a hotspot whose targets
no longer match the passage's links shows up here. Then look at it by hand on
`npm run preview`: a move between rooms plays the door, a move within one does
not.

# Step 7 — Publish and report

Republish the test site, then tell the owner: what changed, every `open`
question for the author, and any image that still misses a fact.

# Rules

- Never type a description into a prompt by hand — change the bible.
- Never paraphrase a quote.
- Never spend money: the Gemini app by hand, not the paid API.
- Nothing from the series folder goes into git.
