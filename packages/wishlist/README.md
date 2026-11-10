# wishlist

A shared gift list for Christmas (Father Christmas and the Three Kings together), and
later for birthdays: a photo of each gift taken in the shop, and anyone with the link
can say "I'll give this one", then mark it bought. Nobody else can buy the same gift
by mistake, and nobody needs an account.

Served at `https://wishlist.jorgelillo.workers.dev`: a Cloudflare Worker on the free
plan with the pages and photos as static assets, and the claims in D1, Cloudflare's
SQLite. Node, outside Bazel, like `interactive_fiction`. The page text is in Spanish.

## How it works

- **The list (`/`)** is public. Each gift is free, reserved or bought, with the time.
  Reserving asks for an optional name, up to 40 characters. Filters by recipient and
  by state sit above the gifts and live in the address (`?para=older&estado=libres`),
  so a link can open one child's list. The recipient is the first level, a solid
  segmented control; the state is the second, lighter chips coloured by state.
- **Recipients are labels, not names** ("Hermano mayor", "Hermano pequeño"), declared
  once in `gifts.json` and referenced by each gift's `for`.
- **Only the browser that reserved a gift can change it.** It gets a random token in
  an HttpOnly cookie that lasts 400 days. D1 keeps only the token's SHA-256. From
  another phone, the gift shows as reserved by someone else.
- **Names are private.** The public state never carries them. `/admin`, behind Basic
  auth, shows who reserved what and can release or mark any gift, for the guest who
  changed phone or forgot.
- **`/admin` on the home screen.** It has its own manifest (`/admin.webmanifest`),
  so "Add to Home Screen" from `/admin` opens `/admin`. Turn off "Open as Web App":
  in Safari the saved password fills in, and a web app never offers it. The admin
  user is `regalos`, not `jorge`. Safari treats every `*.jorgelillo.workers.dev`
  site as one for autofill, so the user name is what tells the logins apart.
- **Photos are public**, so `npm run photo` turns them upright and removes their
  metadata, GPS included, before they enter the repo.

Behaviour and its tests: [`openspec/specs/wishlist/list/spec.md`](../../openspec/specs/wishlist/list/spec.md).

## Layout

```text
wishlist/
├── gifts.json            # The list: title, and each gift's id, title, detail, note, photo
├── photos/               # 1280 px JPEGs without metadata, named after the gift id
├── web/                  # The list page, the admin page, styles and scripts
├── assets/icon.svg       # Home-screen icon; web/ holds it as SVG and 180, 192, 512 px PNGs
├── src/app.ts            # Routes, claims, Basic auth; src/worker.ts only exports it
├── migrations/           # D1 schema
├── scripts/build.ts      # Checks gifts.json and writes dist/ for the Worker
├── scripts/photo.ts      # Takes a photo in: resize, upright, no metadata
├── scripts/jpeg.ts       # Reads EXIF orientation and drops metadata segments
├── scripts/set-admin.sh  # Sets the /admin credentials as Worker secrets
├── tests/                # Vitest; the Worker runs against Node's SQLite
├── wrangler.toml         # Worker, assets and D1 binding
└── deploy/               # Pinned wrangler, kept apart from the test install
```

## Commands

```bash
npm ci                                   # once
npm test && npm run typecheck            # what CI runs
npm run photo -- ~/Downloads/IMG_1234.jpg lego-fire-station   # add a photo
npm run build                            # check gifts.json, write dist/
npm run dev                              # local site with a local D1 at http://localhost:8787
npm run deploy                           # migrations + upload
npm run set-admin                        # once: /admin credentials (user "regalos"), password left on the clipboard
```

Day-to-day steps (adding gifts, a new occasion, fixing a claim) are in
[OPERATIONS.md](OPERATIONS.md).

## Icon

`assets/icon.svg` is the source. After changing it, render the PNGs with headless
Chrome at 180 (`web/apple-touch-icon.png`, iOS), 192 and 512 (`web/icon-*.png`, the
manifest for Android), and copy the SVG to `web/icon.svg`. Use a throwaway
`--user-data-dir` and a new file name each time, because Chrome caches a `file://`
image. A phone keeps the icon it saved, so the shortcut has to be added again.
