# 3D draft

An experiment: the series' chapters with their rooms in 3D. The reader's own
engine runs the passages; a scene listed in the author's `web/3d/worlds.json` is shown as a
Gaussian-splat room (three.js + [Spark](https://sparkjs.dev)), and any other
scene keeps its 2D picture — chapter 1's rooms are all 3D, chapter 2 plays
with its 2D pictures except room 207.

It plays full screen, in landscape (a phone held upright gets a screen asking to turn it): a title screen while the first room
loads, with the reader's credits line, the reader's own menu over the room
(Continuar where the game was left, Empezar or Nueva partida, Capítulos with
each chapter's state, Finales y logros, Ajustes, Créditos with the credit
cards; the panels are translucent so the room stays in sight) and its keys
(Space or Enter continues, Escape steps back). The game is saved at every
passage in the reader's own format (`src/app/save.ts`), endings and explored
passages are recorded for the achievements, and the settings (volume, sound,
text size, effects) are the reader's; the end of a chapter shows its code and the way to the next one, which
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
   the scene to `web/3d/worlds.json` in the author's clone with the vertical field of view and downward
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
   skips. It also fails when the title, "Acerca de" or the "Capítulos" panel
   overflows a 750×330 phone; chapters start from that panel. `npm run fit -- <scene>` (step 4) finds the camera by rendering the
   world and scoring it against the picture.
7. **Preview** — `npm run deploy`. It rebuilds the stories first as a public
   deploy does (`STORIES_PUBLISH=1`: published chapters only, from the
   author's default branch), and `prepare.ts` refuses a built library that
   holds a draft chapter, so what `npm run dev` or `build:drafts` left in
   `public/stories` cannot reach the preview's public URL.

Added to an iPhone's home screen, the draft opens full screen with its own
icon — Cheshire's keychain, painted with `view.ts --aspect 1:1` into
`web/3d/worlds/icon-1024.png`, from which `prepare.ts` makes every size and the
manifest.

The whole procedure, with its traps, is the
[`scene-3d`](../../.claude/skills/scene-3d/SKILL.md) skill.

| Model | Credits | ≈ US$ |
|---|---|---|
| `marble-1.0-draft` (default) | 150 + 80 for the panorama | 0.18 |
| `marble-1.1` (`--full`) | 1,500 + 80 | 1.26 |

## Where things live

- **The 3D art lives in the author's repository**, `web/3d/` (read through
  the package's `stories/samantha` link, by `art.ts`): `worlds.json`, the
  served splats and colliders, the pictures worlds grow from, the cut-outs and
  their masks, the icon, and `prompts/`. It derives from his art, so it is
  never committed to this public repository.
- **`worlds/` here is the workbench** (gitignored): `generate.ts`, `fetch.ts`,
  `view.ts` and `fit.ts --around` write there. A world being tried can be
  listed in his `worlds.json` while its files are still only here — the
  draft reads a file from `web/3d/` first and falls back to `worlds/`. Once
  it is right, copy what the page serves into his `web/3d/worlds/` and open a
  PR to his repo, as for any art. World Labs keeps every world: `node fetch.ts
  <scene> <world id>` downloads one again (the ids are in `worlds.json`).
- A scene is in 3D when `web/3d/worlds.json` has an entry under its id, in any
  chapter. Two entries may point at the same files (one room, two pictures
  of it from the same camera, say with and without a character): the page
  downloads them once, and each entry keeps its own `figures`.
- A full-model world's `<scene>-500k.spz` (~7.5 MiB) is what the page
  loads; its full resolution (~27 MiB) is over Cloudflare's 25 MiB per file.
- **The page downloads no collider.** `prepare.ts` casts every chapter's
  hotspots and cut-outs onto the colliders on disk (`bake.ts`,
  `room-geometry.ts`) and writes their places into the served `worlds.json`
  (`rooms`, keyed `chapter/scene`), beside each world's camera. The meshes —
  61 MB for the fourteen worlds — stay in the author's repository, where
  `fit.ts` and the bake read them. A room costs its splats (~7.2 MB), not
  splats plus mesh.
- **World files are named by their content** (`room-500k.<digest>.spz`) and
  `prepare.ts` writes a `_headers` that lets a browser keep anything under
  `worlds/` for a year (`immutable`); `worlds.json` and the pages are checked
  again on each visit. A changed world is a new name, so an app on an
  iPhone's home screen gets it at once and never downloads an unchanged room
  twice.
- **Loading shows.** The title has a line that fills with the first room's
  download, and so does the fade between rooms when the next one is not in
  yet.
- **Sound** is the reader's: ambience per room, the door, a step on arriving,
  the series' stings, the heartbeat where a series tracks a condition, and a
  mute switch in the corner that shares the reader's setting.
- **The view eases** towards where it is turned and keeps a little of a
  drag's speed on release; the pointer is captured, so a drag that leaves the
  window or is cancelled by the system ends. With reduced motion it follows
  the finger exactly and does not sway.
- `npm run typecheck` here checks the draft's own sources (they are outside
  the package's `tsc`).

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
2D pictures. Saves, achievements and settings are the reader's; undo and the
reader's full end panel are not wired in. A splat world carries the picture's own light,
so the night look is a grade over it; real lights and close-ups of single
objects would need those objects as meshes (the reference the owner liked,
halloween.dev, is built from per-object GLB models).
