# 3D draft

An experiment: chapter 1 of the series with its rooms in 3D. The reader's own
engine runs the passages; a scene listed in `worlds.json` is shown as a
Gaussian-splat room (three.js + [Spark](https://sparkjs.dev)), and any other
scene keeps its 2D picture.

It plays full screen, in landscape (a phone held upright gets a screen asking to turn it): a title screen while the first room
loads; the passage as subtitles, a paragraph at a time (the reader's own
`segment`); things to interact with as soft glows, and touching one moves the
camera towards it and lists its choices; the room graded down to night, with
vignette, grain, a flickering bulb and the reader's synthesized ambience and
door sound. It is outside the site's build and checks, and
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
   pitch that reproduce the picture (room 207: 46° and −9°; the Cheshire room:
   46° and −10°, found by comparing renders with the trimmed picture); the
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
6. **Preview** — `npm run deploy` (after `npm run stories` in the package).

| Model | Credits | ≈ US$ |
|---|---|---|
| `marble-1.0-draft` (default) | 150 + 80 for the panorama | 0.18 |
| `marble-1.1` (`--full`) | 1,500 + 80 | 1.26 |

## Where things live

- The worlds derive from the author's art: `worlds/` and `public/` are
  gitignored, never committed to this public repository.
- `worlds/<scene>-500k.spz` (~5 MB) is what the page loads; Cloudflare serves
  at most 25 MiB per file.

## Not there yet

Chapter 1's three rooms are 3D (room 207, the bathroom, room 207 with
Cheshire, who is part of that world: static and a little soft); the ending is
a picture. The author's own components (the rules as a book page) keep his
stylesheet and get a subtitle to themselves. Saves, achievements and the end-code panel of the real reader are
not wired in. A splat world carries the picture's own light,
so the night look is a grade over it; real lights and close-ups of single
objects would need those objects as meshes (the reference the owner liked,
halloween.dev, is built from per-object GLB models).
