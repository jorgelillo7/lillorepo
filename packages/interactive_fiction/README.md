# interactive_fiction

A web reader for interactive stories written in **Twine 2 with the Harlowe
format**. The author keeps writing in Twine; this package reads his Twee source
(or a published Twine HTML build), checks it, and serves every chapter of a
series from one site: chapter list, autosave, undo, and the end-of-chapter code
carried into the next chapter.

It is a static site (Vite + TypeScript, no runtime dependencies) plus three
Node scripts. It is outside Bazel: the first package in the repo that is not
Python.

## Two repositories, one workflow

The story, and everything about it, lives in the author's repository; this
package is only the reader. Both are cloned side by side
(`~/Projects/project-silent-hill`, `~/Projects/lillorepo`).

| Repository | Folder | What it holds | Who edits it |
|---|---|---|---|
| `project-silent-hill` (the author's, private) | `Capitulo N/fuente/` | The chapter, one `.twee` per scene: what the site reads | The author |
| | `shared/style/`, `shared/logic/` | CSS and passages shared by every chapter | The author |
| | `Capitulo N/build/` | His Tweego build for his Netlify site, and `resources/`, the media the passages use | The author |
| | `bible/`, `prompts/`, `docs/`, `tools/`, `tests/` | His canon, his AI writing workflow, build, lint and walkthrough tests | The author |
| | `Concept Art/` | His character sketches; the generated art uses them as references | The author |
| | `web/` | The reader's own files: `series.json`, scene files, `game.json`, the art bible, the generated images | Us, through PRs he reviews |
| `lillorepo` (public) | `packages/interactive_fiction/` | This reader: engine, site, build, checks, deploy | Us |
| | `stories/<series>` (gitignored) | A link to the author's `web/` folder | — |

**When a chapter changes:**

1. The author writes in `fuente/`, checks it with his `tools/build.sh` and
   walkthrough tests, and merges to his `master`.
2. Here: `git -C ~/Projects/project-silent-hill pull`.
3. `npm run stories`, `npm run explore -- <series>` and `npm run parity`. What
   fails goes back to him by passage name.
4. New rooms or characters: art-bible entries quoted from the text, each image
   listing its passages; `npm run art` generates them; review each against the
   bible; `npm run scenes:draft`, then place the hotspots and check them with
   an overlay ([`scene-art`](.claude/skills/scene-art/SKILL.md)); `npm run play`.
5. Changes to `web/` go to the author as a PR in his repository.
6. `npm run deploy`.

**From text to a 3D room (experiment).** The same story, one layer further:

1. **The author's repository** — the chapter text, in `fuente/`.
2. **Google AI Studio (Gemini, paid key)** — `npm run art` turns the art
   bible into each room's picture (about US$0.12 an image); the 2D reader uses
   it as is.
3. **World Labs (paid key)** — that picture becomes a 3D room:
   [`experiments/draft3d`](experiments/draft3d/README.md) generates the world,
   projects the scene file's hotspots onto it, and runs the chapter in a
   preview Worker, never the public one (about US$0.18 a draft world,
   US$1.26 a full one).

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

A chapter's `source` can also be a list of folders and files, as Tweego takes
them — `["shared/style", "Capitulo 1/fuente"]` — whose `.twee` passages and
`.css` stylesheets make one story (a `.js` script is refused).

When the author keeps the chapters in his own repository, `"sourceRoot":
"~/Projects/<his repo>"` (absolute, relative to the series folder, or under
`~/`) makes every `source` and the optional per-chapter `"resources"` folder
resolve inside his clone, read in place — see OPERATIONS.md, "The author
hand-off".

An optional `"credits"` list — `{ "name", "role", "links": { "GitHub": "https://…" } }`
per person — shows who made the series on "Acerca de" and under the title
screen's menu; links must be https.

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
- **An area appears only when some of its `targets` are links the passage
  offers right now**, so the story's own `(if:)`s decide what can be clicked.
  One offered target is a plain click.
- **Several offered at once open a menu** beside the area: the standard for
  choices that go through one object, such as a door's three exits or the
  answers given to a character. Give the object one area listing every target.
- **An area with a `view` steps through to another scene** for the same
  passage (`{ "label": "Out to the corridor", "targets": [], "view": "corridor", … }`).
  The picture changes, with the door if the room does, and the text stays.
  The passage's choices appear on what they lead to in that picture: the
  stairs, the end of the corridor. Use it when a passage's exits are seen
  from somewhere else; it shows only when that view holds a choice the
  passage offers.
- Links with no area stay as buttons in the text.
- The build fails on a scene that names a missing passage, a target that is not
  a passage, a missing image, an area with no rectangle yet, a `view` that is
  not a scene of the file, or an area with neither targets nor a view. Scene images live in the series folder
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
  `find: _x where …, ...`, `input: bind $v`, `text-colour`, `dm` (`datamap`).
- **Datamaps:** read with `$map's key` or `$map's (expression)` (in macros and
  in text), set with `(set: $map's key to …)`; `contains` asks about keys. As
  in Harlowe, a map is copied on assignment, so changing a key changes only
  that variable.
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
| `scripts/series.ts` | Reads a series: its manifest, its chapters (one file, or Tweego-style folders), where its sources live |
| `scripts/art-bible.ts`, `scripts/prompts.ts` | The art bible's checks, and the prompts composed from it |
| `scripts/art.ts` | Generates planned images through the Gemini API and registers them in the bible |
| `scripts/scene-draft.ts` | A chapter's first scene file from the art bible, hotspots still to place |
| `scripts/parity.ts`, `scripts/chrome.ts` | Every page compared with real Harlowe in headless Chrome; the Chrome driver it shares with `play` |
| `tests/` | Vitest, on `tests/fixtures/mini.twee` — a story written for the tests |
| `experiments/draft3d/` | The 3D draft: generated worlds with the scene hotspots projected onto them, its own preview Worker; outside the site's build and checks |

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
npm run parity -- <series> --harlowe <Twine build.html>   # every page compared with real Harlowe, line breaks included
npm run scenes:draft -- <series> <chapter>    # a first scene file from the art bible, hotspots still to place
npm run art -- <series> [ids] [--dry-run]     # generate planned images (paid Gemini API key in GEMINI_API_KEY)
```

Scripts run TypeScript directly on Node ≥ 24 (type stripping), no build step.
