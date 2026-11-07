# interactive_fiction — operations

## The author hand-off

**Where his chapters live:** his own private git repository, cloned beside
this one (`~/Projects/<his repo>`). `series.json` points `sourceRoot` at the
clone and each chapter's `source` / `resources` at his files, so the build
reads them in place — nothing is copied. A chapter is his Tweego source as
his `tools/build.sh` compiles it — the shared stylesheet folder plus the
chapter's `fuente/` folder, one `.twee` per scene — so there is no generated
copy to keep in step; the media its passages reference is the folder its
`resources` entry names. The series folder here keeps only what is ours: scene
files, the art bible, `game.json`, the generated art.

**Each delivery:** he pushes and says draft or final, and what changed.

**What keeps a chapter importable**

- Only the macros and markup listed in the README. Anything else fails
  `npm run stories` with the passage name; then we add support or he rewrites
  that line.
- One `startup` passage per chapter that sets every variable.
- The chapter's end code in one variable, asked for by the next chapter with
  `(input: bind $…)` and checked against a list — the `carry` pair in
  `series.json`.

**What we send back after each delivery**

1. `npm run stories` output — errors (unsupported syntax, broken links,
   variables read but never set) and warnings (variables set but never read).
2. `npm run explore` — unreachable passages, dead ends, every reachable end
   code, runtime errors, and the codes of the previous chapter that the new
   one treats like a wrong code.
3. The test URL.

## Art for point-and-click

Each scene is one image per room plus its clickable areas. The areas are
percentages of the image, so they survive a resize but not a re-drawn room: new
art means re-measuring the rectangles in the chapter's scene file. Who makes
the art (the author, an illustrator, generated) and under what licence is
decided per series before any of it is published.

**Generating it with AI:** `npm run art -- <series>` sends every planned
image of the art bible to the Gemini API: the composed prompt, plus the image
an edit changes — or else the bible's `styleReference` and each character's
`reference` (the author's concept art) — and saves the full-size original in
`art-originals/`, a 1600 px copy in `scenes/`, and the exact prompt in the
bible. A variant of a room (someone on the bed, a door ajar) is an edit of the
first image, not a new one, so the room stays the same.

- **It costs money.** Image models have no free tier in the API (the free
  key answers 429 with a limit of 0). About US$0.12 per 2K image with the
  default `gemini-3.1-flash-image`; a chapter of a dozen rooms with a few
  retries is about US$2–3.
- **The key:** a paid Gemini API key in `GEMINI_API_KEY`, for the shell only,
  never written to a file. Use a project with a daily cap on the image model,
  so a mistake is bounded in money. `be_water`'s paid key works, and has one
  (see its OPERATIONS, "Two Gemini keys"):
  `export GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=be-water-secrets --project be-water-app | python3 -c "import sys,json;print(json.load(sys.stdin)['gemini_api_key_paid'])")`
- **Before paying:** `--dry-run` prints each request and the estimated cost;
  `--max N` (default 15) caps the calls of one run.
- **A detail that comes out wrong** is fixed with `--note "…"` on that image,
  appended to its prompt and recorded with it. Each call is paid, so look at
  the result before asking again.

Review every image against the bible before a scene uses it, then place the
rectangles and check them with an overlay. Say on the series' "about" page
that the art is generated. Without a key, `npm run prompts -- <series>` prints
the same prompts for the Gemini app, by hand.

## Updating a chapter

```bash
git -C ~/Projects/<his repo> pull
npm run stories && npm run explore -- <series>
npm run parity -- <series> --harlowe "$HOME/Projects/<his repo>/Capitulo 1/build/index.html"
npm run build && npm run preview     # check it at http://localhost:4173
npm run deploy
```

## Deploying (Cloudflare Workers static assets)

Static assets on Cloudflare are free and unlimited; Firebase Hosting's free
plan caps transfer at 360 MB/day, which a few readers with images exhaust.
Cloudflare has folded Pages into Workers, and wrangler 4 refuses to create a
new Pages project without `--force`, so the reader is a Workers project that
serves `dist/` as static assets and runs no code.

**Once:** a free Cloudflare account, then `npm run deploy:login` in this
package (opens the browser; wrangler keeps the login on this Mac). The first
deploy registers the account's `workers.dev` subdomain.

**Every deploy:** `npm run deploy` — builds (drafts left out) and uploads
`dist/` to the project named in `wrangler.toml` (`interactive-fiction`). The site is
at `https://interactive-fiction.jorgelillo.workers.dev`.

`wrangler` lives in `deploy/` with its own lockfile, pinned, so the test job
never installs its ~270 MB. To show the author a draft chapter, deploy
`npm run build:drafts` output under another name
(`deploy/node_modules/.bin/wrangler deploy --name interactive-fiction-draft`), never
to the public one.

**From CI, later:** a Cloudflare API token scoped to Workers edit and the
account id as GitHub secrets. CI cannot build the stories (not in the repo), so
it would pull `stories/` from the private bucket first. Not set up.

## Backing up the stories

The author's chapters and media are in his git repository, which is their copy
of record. What is ours — scene files, the art bible, `game.json`, the
generated art and its prompts — lives only in `stories/<series>/` on this Mac
until it gets a backup of its own (see `PENDING.md`).
