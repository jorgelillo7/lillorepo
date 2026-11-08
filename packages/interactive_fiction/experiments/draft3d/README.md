# 3D draft

An experiment: the series' chapters with their rooms in 3D. The reader's own
engine runs the passages; a scene listed in `worlds.json` is shown as a
Gaussian-splat room (three.js + [Spark](https://sparkjs.dev)), and any other
scene keeps its 2D picture — chapter 1's rooms are all 3D, chapter 2 plays
with its 2D pictures except room 207.

It plays full screen, in landscape (a phone held upright gets a screen asking to turn it): a title screen while the first room
loads, with the reader's credits line, a menu of words (each chapter, "Acerca
de" with the credit cards) and its keys (Space or Enter reads on, Escape steps
back); the end of a chapter shows its code and the way to the next one, which
starts with that code carried in (`series.carry`, as the reader does); the passage as subtitles, a paragraph at a time (the reader's own
`segment`); things to interact with as soft glows, and touching one moves the
camera towards it and lists its choices; the room graded down to night, with
vignette, grain, a flickering bulb and the reader's synthesized ambience and
door sound. Moving between rooms fades to black (a thin loading line only if
the next room is still downloading); after the first room, the others
download in the background. Page zoom is off: a double tap used to throw the
view off screen. It is outside the site's build and checks, and
deploys to its own Worker:
<https://interactive-fiction-draft3d.jorgelillo.workers.dev>.

## The flow

1. **Text** — the author's repository (`Capitulo N/fuente/`).
2. **Picture** — `npm run art` in the package: Gemini through Google AI Studio,
   a paid key (`GEMINI_API_KEY`).
3. **World** — `node generate.ts <scene> [--full] [--dry-run]` here: World
   Labs Marble, a paid key (`WORLDLABS_API_KEY`). It trims the picture's dark
   frame first — a framed picture comes back as a painting hung in an invented
   room — and downloads the splats and the collider mesh into `worlds/`.
4. **Fit** — the world's starting camera is usually the picture's camera. Add
   the scene to `worlds.json` with the vertical field of view and downward
   pitch that reproduce the picture, as `npm run fit -- <scene>` finds them
   (room 207: 47° and −9°; the Cheshire room: 46° and −9°); the
   hotspots of the scene file are then cast from that camera onto the
   collider, so none is placed by hand. When the world did not grow from the
   picture's viewpoint, give it a `camera` position and place its hotspots by
   hand in `anchors` (fractions of its own view); a hotspot with no place in
   the room stays a text choice — the last resort, not the habit.
5. **A better picture, when the scene's own one is wrong for 3D** — the
   bathroom was painted from its doorway, which left nothing to turn to and no
   door to leave by. `node view.ts <name> <prompt-file> <references…>` paints
   another view of the same room with Gemini (about US$0.12) into `worlds/`,
   and `generate.ts <scene> --image worlds/<name>.jpg` builds the world from
   it; `worlds.json` records it under `picture`. The bathroom's new view, from
   inside, holds the mirror and the open door back to room 207, so both are
   places in the room.
6. **Check** — `npm run check` plays chapter 1 to an ending by exploring,
   at a phone in landscape, and fails on a choice found nowhere or a console
   error; `npm run check -- 02` plays chapter 2, and `-- 02 --via 207` takes
   the shortest path through a given passage, for a room the shortest path
   skips. It also fails when the title or "Acerca de" overflows a 750×330
   phone. `npm run fit -- <scene>` (step 4) finds the camera by rendering the
   world and scoring it against the picture.
7. **Preview** — `npm run deploy` (after `npm run stories` in the package).

Added to an iPhone's home screen, the draft opens full screen with its own
icon — Cheshire's keychain, painted with `view.ts --aspect 1:1` into
`worlds/icon-1024.png`, from which `prepare.ts` makes every size and the
manifest.

The whole procedure, with its traps, is the
[`scene-3d`](../../.claude/skills/scene-3d/SKILL.md) skill.

| Model | Credits | ≈ US$ |
|---|---|---|
| `marble-1.0-draft` (default) | 150 + 80 for the panorama | 0.18 |
| `marble-1.1` (`--full`) | 1,500 + 80 | 1.26 |

## Where things live

- The worlds derive from the author's art: `worlds/` and `public/` are
  gitignored, never committed to this public repository. Their only copies
  are this Mac's `worlds/` and World Labs itself: `node fetch.ts <scene>
  <world id>` downloads one again, and every world's id is in `worlds.json`.
  The cut-out PNGs and the Gemini pictures (`view.ts` outputs) exist only in
  `worlds/`; back them up with the author's `web/` art if they matter.
- A scene is in 3D when `worlds.json` has an entry under its id, in any
  chapter. Two entries may point at the same files (one room, two pictures
  of it from the same camera, say with and without a character): the page
  downloads them once, and each entry keeps its own `figures`.
- A full-model world's `worlds/<scene>-500k.spz` (~7.5 MiB) is what the page
  loads; its full resolution (~27 MiB) is over Cloudflare's 25 MiB per file.
- Every build stamps `worlds.json`, and the page asks for each world file
  with that stamp: an app on an iPhone's home screen otherwise keeps an older
  file after a deploy.

## Operating notes

- **Keys.** `WORLDLABS_API_KEY` is in `~/.zprofile` (key
  `lillorepo-interactive-fiction`; credits and billing at
  <https://platform.worldlabs.ai/billing>, auto-refill off). Tools that need
  it run in a login shell (`zsh -lc '…'`). `GEMINI_API_KEY` is be-water's
  paid key, command in the package's `OPERATIONS.md`; on this account Gemini
  spend has been covered by Google Cloud promo credits, so it has far more
  room than World Labs' prepaid balance: spend pictures freely to make each
  world right first time.
- **What a call really costs** (World Labs reports it): one picture, draft
  230 credits, full 1,580; with three extra views (`--views`), 250 / 1,600.
  US$1 = 1,250 credits. A Gemini picture or edit ≈ US$0.12.
- **Moderation.** World Labs refuses some requests with `403 … Violence`
  before charging; rust or red streaks read as blood. Rejections are free:
  bisect the pictures, then desaturate the red or repaint without it.
- **Gemini edits stay aligned to the pixel** (a removed character, a green
  matte), which is what makes `cutout.py` work; new views it paints from
  another angle do not agree with each other, which is why worlds are grown
  from one picture.
- **`fit.ts` needs a GPU-backed Chrome** (the default headless one on this
  Mac); with SwiftShader the splats do not draw.
- **Chapter 1 cost**, all attempts included: ≈ US$10 of World Labs credits
  and ≈ US$2 of Gemini pictures. With the method settled, a similar chapter
  is about three full worlds (≈ US$3.80) plus a few pictures.

## Not there yet

Chapter 1's three rooms are full-model World Labs worlds, each grown from one
picture (coherent inside it), turning within bounds that stop short of what
the world invented past the picture's edges. Cheshire is not part of her
room's world: the world grew from the room painted without her, and she is a
sharp cut-out from the original picture laid onto the bed (`figures`). Each
room serves its 500k splats (~7 MiB): full resolution is over 25 MiB.

The ending is a picture. The author's own components (the rules as a book
page) keep his stylesheet and get a subtitle to themselves. Cheshire is still
(a cut-out does not move). Chapter 2's rooms other than 207 are still their
2D pictures. Saves, achievements, settings and the full end panel of the real
reader are not wired in: the draft keeps only each chapter's end code, to
carry it into the next. A splat world carries the picture's own light,
so the night look is a grade over it; real lights and close-ups of single
objects would need those objects as meshes (the reference the owner liked,
halloween.dev, is built from per-object GLB models).
