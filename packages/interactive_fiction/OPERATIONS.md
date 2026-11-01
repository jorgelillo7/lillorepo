# interactive_fiction — operations

## The author hand-off

**Where his chapters live:** his own private git repository, cloned beside
this one (`~/Projects/<his repo>`). `series.json` points `sourceRoot` at the
clone and each chapter's `source` / `resources` at his files, so the build
reads them in place — nothing is copied. A chapter is his Twee source
(`Capitulo N/src/*.twee`); the media its passages reference is his build's
`resources/` folder. The series folder here keeps only what is ours: scene
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

**Generating it with AI:** one consistent style prompt for every room plus a
scene description taken from the passage text, 16:9, all rooms in one chat so
the style holds; a variant of a room (someone on the bed, a door ajar) is an
edit of the first image, not a new one. Keep the prompts and the full-size
originals next to the art in the series folder — they are not published.
Resize to ~1600 px wide for the web, then place the rectangles and check them
with an overlay before shipping. The Gemini API's free tier allows no image
generation, so this runs in the Gemini app, by hand. Say so on the series'
"about" page.

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
`dist/` to the project named in `wrangler.toml` (`historias`). The site is at
`https://historias.interactive-fiction.workers.dev`.

`wrangler` lives in `deploy/` with its own lockfile, pinned, so the test job
never installs its ~270 MB. To show the author a draft chapter, deploy
`npm run build:drafts` output under another name
(`deploy/node_modules/.bin/wrangler deploy --name historias-borrador`), never
to the public one.

**From CI, later:** a Cloudflare API token scoped to Workers edit and the
account id as GitHub secrets. CI cannot build the stories (not in the repo), so
it would pull `stories/` from the private bucket first. Not set up.

## Backing up the stories

The author's chapters and media are in his git repository, which is their copy
of record. What is ours — scene files, the art bible, `game.json`, the
generated art and its prompts — lives only in `stories/<series>/` on this Mac
until it gets a backup of its own (see `PENDING.md`).
