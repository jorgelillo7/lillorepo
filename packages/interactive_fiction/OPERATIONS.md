# interactive_fiction — operations

## The author hand-off

**What he sends, per chapter**

- The Twee export from Twine: *Library → select the story → Build → Export As
  Twee*. One file per chapter, named `NN-slug.twee`.
- Images in a folder that mirrors the paths used in the passages
  (`resources/images/…`). WebP or JPEG under 500 KB each is plenty.
- One line: draft or final, and what changed.

**Channel:** a shared Google Drive folder with `capitulos/` and `resources/`.
He overwrites the files there; we copy them into `stories/<series>/`.

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
cp ~/Downloads/03-chapter.twee stories/<series>/
npm run stories && npm run explore -- <series>
npm run build && npm run preview     # check it at http://localhost:4173
```

## Deploying (Cloudflare Pages)

Static assets on Cloudflare Pages are free and unlimited; Firebase Hosting's
free plan caps transfer at 360 MB/day, which a few readers with images exhaust.

**Once:** a free Cloudflare account, then `npm run deploy:login` in this
package (opens the browser; wrangler keeps the login on this Mac).

**Every deploy:** `npm run deploy` — builds (drafts left out) and uploads
`dist/` to the Pages project named in `wrangler.toml` (`historias`), creating it
on the first run. The site is at `https://historias.pages.dev` or, if that name
is taken, the one wrangler prints.

`wrangler` lives in `deploy/` with its own lockfile, pinned, so the test job
never installs its ~270 MB. To show the author a draft chapter, deploy
`npm run build:drafts` output to a separate project
(`deploy/node_modules/.bin/wrangler pages deploy dist --project-name <name>-borrador`),
never to the public one.

**By hand instead:** Workers & Pages → Create → Pages → Upload assets, and
drag `dist/` from `npm run build`.

**From CI, later:** a Cloudflare API token scoped to Pages edit and the
account id as GitHub secrets. CI cannot build the stories (not in the repo), so
it would pull `stories/` from the private bucket first. Not set up.

## Backing up the stories

`stories/` is local only. Until there is a private bucket prefix for it (same
pattern as the draft season data), the copy of record is the author's Drive
folder.
