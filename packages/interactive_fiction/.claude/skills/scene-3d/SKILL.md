---
name: scene-3d
description: Turn a point-and-click chapter's rooms into 3D in the draft — a World Labs world per room grown from its picture, the camera fitted so the scene file's hotspots land on their objects, a new picture painted when the scene's own is wrong for 3D, the chapter played through by exploring, and a preview the author can open. Use when a chapter (or a room) should be tried in 3D, or a 3D room looks wrong.
---

# Goal

The same chapter, played in rooms you can look around instead of pictures.
The author writes; the pictures come from the art bible (the `scene-art`
skill); every room's 3D world grows from its picture, so the style stays the
one the bible fixed and the rooms stay consistent with one another. Nothing
is placed by hand unless the world forces it.

This is the experiment in `experiments/draft3d/` — outside the site's build,
on its own Worker (<https://interactive-fiction-draft3d.jorgelillo.workers.dev>).
Read its `README.md` first, and `docs/technical/parked-work.md` § "a 3D draft
of chapter 1" for what was measured. Bringing 3D into the reader itself goes
through `openspec-propose` first.

# The flow

```
author's text  →  picture (Gemini, scene-art)  →  world (World Labs)  →  fit  →  check  →  preview  →  author
   his repo          npm run art                    generate.ts            fit.ts   check.ts   npm run deploy
```

| Step | Tool (in `experiments/draft3d/`) | Cost |
|---|---|---|
| A room's picture | `npm run art` in the package (`scene-art`) | ≈ US$0.12 |
| Another view of a room, when its picture is wrong for 3D | `node view.ts <name> <prompt-file> <references…>` | ≈ US$0.12 |
| A world | `node generate.ts <scene> [--image …] [--trim X,Y] [--full]` | ≈ US$0.18 draft · ≈ US$1.26 full |
| The camera | `npm run fit -- <scene>` | free |
| Play it through | `npm run check` | free |
| Preview | `npm run deploy` | free |

Every paid call needs the owner's OK first; `--dry-run` prints the cost.
Keys: `WORLDLABS_API_KEY` (in `~/.zprofile`) and `GEMINI_API_KEY` (command in
`OPERATIONS.md` § "Art for point-and-click").

# Step 1 — Look at the picture before paying for a world

A world grows from one picture, and the picture decides whether it works:

- **A dark frame** (the series' rounded vignette, letterbox bands) comes back
  as a painting hung in an invented room. `generate.ts` trims 3.5 % by
  default; measure anything thicker and pass `--trim X,Y` (pixels from each
  side, from top and bottom).
- **A room seen from outside** (the bathroom, painted from its doorway) comes
  back with the camera somewhere else and nothing to turn to — no door to
  leave by. Paint a view from inside with `view.ts` that holds what the
  passages need (the mirror *and* the door back), using the room's picture and
  the next room's as references, then build the world from it with
  `--image`. Say "eye height" and "no border, no frame" in the prompt: the
  bible's style asks for a high corner angle.
- **A person** comes out soft and static: the world bakes them in. Fine for a
  draft; for a sharp one, make the character a separate element.

# Step 2 — Generate the world

```bash
node generate.ts <scene> --dry-run
node generate.ts <scene> [--trim X,Y] [--image worlds/<view>.jpg] --prompt "Interior of …"
```

It downloads the 500k and 100k splats and the collider into `worlds/` (never
committed: they derive from the author's art) and prints the `crop` to record.
Open the world's thumbnail before going further; a painting-in-a-room or a
camera in the wrong place is cheaper to catch now.

# Step 3 — Fit the camera

Add the scene to `worlds.json` (`world`, `splats`, `collider`, `crop`, and
`picture` when it came from `--image`), then:

```bash
npm run fit -- <scene>
```

It renders the world in headless Chrome and searches the vertical field of
view and pitch that reproduce the picture. **Score ≥ 0.8**: write `fovY` and
`pitch`; the scene file's hotspots are cast from that camera onto the
collider and land on their objects. Chapter 1 fitted at 0.93–0.95. **Score
≈ 0.3**: the world did not grow from the picture's viewpoint — repaint the
view (step 1) rather than patch it; as a last resort set `camera` and place
the hotspots by hand in `anchors` (fractions of the world's own view).

A world whose picture is not the scene's own (`--image`) needs `anchors` for
its hotspots, since the scene file's rectangles belong to the old picture.

Then **walk its edges**: turn as far as the draft lets you, both ways. Past
the picture's edges the world invents, and what it invents can contradict
the story — room 207 grew a third door beyond the desk, the author spotted
it. Set `bounds` (degrees from straight ahead, right negative) just short of
anything invented that should not be there; the draft keeps the view's edges
inside them on any screen.

# Step 4 — Play it through

```bash
npm run stories          # in the package: the chapter data the draft reads
npm run check            # in experiments/draft3d
```

The shortest path to an ending, every choice made by touching its thing in
the room when the room holds it, else in the text; fails on a choice found
nowhere or a console error. Only choices with nothing to touch should come
from the text — "Fin del capítulo", say. A choice the room should hold but the
text offers means a hotspot without a place: fix the world, not the rule.

# Step 5 — Preview and the author

```bash
npm run deploy           # the draft's own Worker, never the public reader
```

Open it on a phone in landscape too — headless Chrome does not apply Safari's
text inflation or its bars. Added to the home screen it opens full screen,
without Safari's bars: that is the way to play it on an iPhone, and the title
screen says so. The icon is `worlds/icon-1024.png` (Cheshire's keychain,
painted with `view.ts … --aspect 1:1`, its frame trimmed: the phone rounds the
corners); `prepare.ts` makes every size and the manifest from it. Then the author: what changed, the link, and what
is still a draft (quality, characters).

# What went wrong once, and why the rule exists

| Rule | Because |
|---|---|
| Trim the frame before generating | The vignette made room 207 a framed painting in an invented room |
| Paint a view from inside for rooms painted from outside | The bathroom's world put the camera by the sink and nothing behind it |
| Fit, do not eyeball | The fit finds the camera to a degree; by eye the hotspots drift |
| Choices the room holds leave the text | Choosing from the text skips the exploring, which is the point |
| `[hidden]` wins over layout rules | A hidden 3D canvas kept drawing under a broken 2D picture |
| Images keep the chapter's path (`stories/<series>/scenes/…`) | Serving them elsewhere showed a broken image on the iPhone |
| `text-size-adjust: 100%` | Safari enlarged each subtitle by a different amount in landscape |
| Phones play in landscape only | In portrait the room's sides fall off screen |
| No page zoom (`touch-action`, viewport, Safari's gesture events) | A double tap zoomed the page, threw the buttons off screen, and nothing in the game could undo it |
| Rooms change behind a fade, and the next rooms preload | Entering the bathroom while its world downloaded looked like a freeze |
| Turning stops at `bounds`, and a wide screen never shows wider than the picture | Room 207 and the Cheshire room grew a door past the desk that the story does not have |
