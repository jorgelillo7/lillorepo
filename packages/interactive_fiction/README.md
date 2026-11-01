# interactive_fiction

A web reader for interactive stories written in **Twine 2 with the Harlowe
format**. The author keeps writing in Twine; this package reads his Twee source
(or a published Twine HTML build), checks it, and serves every chapter of a
series from one site: chapter list, autosave, undo, and the end-of-chapter code
carried into the next chapter.

It is a static site (Vite + TypeScript, no runtime dependencies) plus three
Node scripts. It is outside Bazel: the first package in the repo that is not
Python.

## How a story gets in

Stories are **not in git** — the repo is public and the text belongs to its
author. They live in `stories/<series>/` (gitignored):

```
stories/<series>/
├── series.json              # title, chapter order, draft flags, code carry
├── 01-first-chapter.twee    # Twee 3 export (or a published .html build)
├── 02-second-chapter.twee
└── resources/images/…       # the paths the passages use
```

```json
{
  "title": "Series title",
  "chapters": [
    { "id": "01", "source": "01-first-chapter.twee" },
    { "id": "02", "source": "02-second-chapter.twee", "draft": true }
  ],
  "carry": { "from": "end_code", "to": "previous_code" }
}
```

An optional `"about": ["…", "…"]` adds an "Acerca de" page to the series
(credits, and how the art was made).

`carry` names the variable that holds a chapter's end code and the
`(input: bind …)` variable of the next chapter that asks for it. A chapter
marked `draft` is left out of `npm run build`; `npm run build:drafts` and
`npm run dev` include it, so an unpublished chapter never reaches a public
upload by accident. The reader
pre-fills that field with the code the reader earned, so the story still works
unchanged in the author's own Twine builds.

The hand-off with the author — what he sends, how, and what we send back — is
in [OPERATIONS.md](OPERATIONS.md).

## Point-and-click mode

A chapter can carry a **scene file** (`"scenes": "01-scenes.json"` on the
chapter in `series.json`). Passages listed in it are shown as an image with
clickable areas beside the text; the rest, and every chapter without one, are
read as text. The toolbar switches between the two.

```json
{
  "scenes": {
    "room": {
      "image": "scenes/room.jpg",
      "room": "cell",
      "aspect": [16, 9],
      "hotspots": [
        { "label": "Door", "targets": ["Door", "Leave"], "rect": [51, 25, 11, 45] }
      ]
    }
  },
  "passages": { "Start": "room", "Door": "room" }
}
```

- `rect` is `[x, y, width, height]` in percent of the image.
- **An area appears only when one of its `targets` is a link the passage offers
  right now**, so the story's own `(if:)`s decide what can be clicked; the
  first target offered wins. Links with no area stay as buttons in the text.
- The build fails on a scene that names a missing passage, a target that is not
  a passage, or a missing image. Scene images live in the series folder
  (`scenes/`, `resources/`), out of git like the text.

The engine side is `src/engine/scenes.ts` (`hotspotsFor`, `validateScenes`).
Moving between scenes of two different `room`s plays a short door-opening
transition (click to skip; skipped when the reader prefers reduced motion);
two views of the same room, or a scene with no `room`, change without it.

Only media files (images, audio) under `scenes/` and `resources/` are
published; prompts, scripts and originals kept beside them stay local.

## Game layer

A series may add `stories/<series>/game.json` — checked at build against the
chapters, like the scenes:

```json
{
  "title": { "image": "scenes/key-art.jpg", "warning": "Content warning…" },
  "audio": {
    "default": "drone",
    "rooms": { "cell": "hum", "bathroom": "drip" },
    "tags": { "floor-3": "wind" },
    "stings": [{ "chapter": "02", "passage": "The Attack" }]
  },
  "documents": [{ "chapter": "02", "passage": "Diary", "title": "Diario" }],
  "condition": {
    "variable": "sanity",
    "states": [{ "value": 4, "label": "Normal", "level": "fine" }, { "value": 1, "label": "Pánico", "level": "critical" }],
    "hideAuthorHud": "#hud"
  },
  "inventory": {
    "variable": "items",
    "items": { "Knife": { "quote": { "chapter": "02", "passage": "Room", "text": "A sentence from the story." } } }
  }
}
```

What it gives the reader:

- **Sound**, synthesized with the Web Audio API (no files): `hum`, `drip`,
  `drone`, `wind` per room or tag, doors between rooms, steps, a sting on the
  listed passages, a heartbeat when the condition is bad. Starts on the first
  tap; mute in the toolbar.
- **Paragraph-by-paragraph reading**, hotspots after the text.
- **Status**: a heartbeat line with the author's own condition words, an
  inventory where examining shows a quoted sentence; condition effects on the
  page (off under reduced motion or the setting).
- **Documents** on their own sheet.
- **Title screen**, **settings**, and at each chapter's end **"Tu camino"**
  (endings found of all, as ???, choices, places seen) plus a page of endings
  and generic achievements. The build explores every chapter to know its
  endings.

## Art bible

A series may keep `stories/<series>/art-bible.json`: one English description per
character and place, each backed by sentences quoted verbatim from the story,
and a register of every image (place, characters, the shot, the image it edits,
the prompt that made it). `npm run prompts -- <series>` composes the prompts for
the planned images from it, and the build fails when a quote is no longer in
the text, a scene image is not registered, or a generated image has no prompt
recorded. The whole procedure — new chapter to published scene — is the
[`scene-art`](.claude/skills/scene-art/SKILL.md) skill.

## What it supports

A deliberate subset of Harlowe 3, the one the stories use. Anything else fails
the build with the passage name, so nothing renders silently wrong.

- **Macros:** `set`, `if`, `unless`, `else`, `else-if`, `cond`, `display`,
  `goto`, `link`, `a`, `for: each _x, ...`, `print`, `str`, `uppercase`,
  `find: _x where …, ...`, `input: bind $v`, `text-colour`.
- **Operators:** `is`, `is not`, `is in`, `contains`, `and`, `or`, `not`,
  `< > <= >=`, `+ - * /` (`+` joins strings and arrays).
- **Markup:** `[[label|target]]` (and `->`, `<-`), hooks, `{collapsed}`,
  `''bold''`, `//italic//`, raw HTML, `$variables` in text.
- **Tags:** `startup` runs once, `header` renders above every passage; the
  rest are passed to the author's CSS as `<tw-passage tags="…">`.

Not supported: story JavaScript, `(either:)`/`(random:)`, named hooks,
`(history:)`, save macros, audio. Add them when a story needs them.

## Layout

| Path | What |
|---|---|
| `src/engine/` | Pure TypeScript, no DOM: `source` (Twee/HTML), `macros` (the supported list), `markup` and `expr` (parsers), `runtime`, `validate`, `explore`, `scenes`, `game`, `discoveries`, `text` |
| `src/app/` | The site: `main` (routes), `title`, `library`, `achievements`, `reader` (session and events), `views` (its HTML), `progression` (pure: moving, undo, endings), `pacing`, `hud`, `audio`, `settings`/`settings-ui`, `door`, `save`/`storage` (localStorage) |
| `src/app/styles/` | One sheet per component, imported in order from `main.ts`; `harlowe.css` approximates Harlowe's default look |
| `src/contract.ts` | The shapes of `public/stories/`, shared by the build and the app |
| `scripts/build-stories.ts` | Validates every series and writes `public/stories/` |
| `scripts/explore.ts` | Plays every path; the report for the author |
| `scripts/play.ts` | Clicks each chapter's shortest path to an ending in a real Chrome — hotspots and links alike, codes typed — and fails on a missing choice, no end panel, or a console error |
| `scripts/art-bible.ts`, `scripts/prompts.ts` | The art bible's checks, and the prompts composed from it |
| `tests/` | Vitest, on `tests/fixtures/mini.twee` — a story written for the tests |

## Commands

```bash
npm ci                 # once
npm run stories        # validate + build stories/ into public/stories/
npm run dev            # local site with hot reload
npm run build          # stories (no drafts) + typecheck + dist/
npm run build:drafts   # the same, drafts included — never upload this one publicly
npm run preview        # serve dist/ on localhost:4173
npm run deploy:login   # once: log wrangler in to Cloudflare
npm run deploy         # build (no drafts) and upload to Cloudflare (Workers static assets)
npm run explore        # path report for every series (or: npm run explore -- <series>)
npm run prompts -- <series>   # image prompts for the planned images, from the art bible
npm test               # engine tests
npm run play           # every built chapter played end to end in headless Chrome (needs Chrome)
```

Scripts run TypeScript directly on Node ≥ 24 (type stripping), no build step.
