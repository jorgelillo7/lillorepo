# wishlist

A shared gift list for Christmas (Father Christmas and the Three Kings together), and
later for birthdays: a photo of each gift taken in the shop, and anyone with the link
can say "I'll give this one", then mark it bought. Nobody else can buy the same gift
by mistake, and nobody needs an account.

Served at `https://wishlist.jorgelillo.workers.dev`: a Cloudflare Worker on the free
plan with the pages as static assets, and the gifts, their photos and the claims in D1,
Cloudflare's SQLite. Node, outside Bazel, like `interactive_fiction`. The page text is in Spanish.

## How it works

- **The list (`/`)** is public. Each gift is free, reserved or bought, with the time.
  Reserving asks for an optional name, up to 40 characters. Filters by recipient and
  by state sit above the gifts and live in the address (`?para=older&estado=libres`),
  so a link can open one child's list. The recipient is the first level, a solid
  segmented control; the state is the second, lighter chips coloured by state.
- **The list lives in D1**, not in the repo: events, their recipients and gifts
  (`/api/list`). `gifts.json` and `photos/` are only the first Christmas list, imported
  once by `migrations/0003_seed_gifts.sql`; editing them changes nothing on the site.
  Each gift belongs to an event, and the one marked current is shown.
- **Recipients are labels, not names** ("Hermano mayor", "Hermano pequeño"), stored per
  event and referenced by each gift.
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
- **Gifts are added from `/admin`**, on the phone: a name, who it is for, optional
  detail and note (shop, price, model), and a photo from the camera or the library. The
  page redraws the photo through a canvas (1280 px, JPEG) before uploading, which drops
  its EXIF and GPS and keeps the upload small; the Worker then rebuilds it as a plain
  baseline JPEG, cutting any metadata and anything appended after the image, and refuses
  anything else. Each gift can be edited, hidden or deleted; a gift someone reserved
  asks twice before it is deleted.
- **Photos are public**, so none carries where it was taken. Uploaded ones are stored in
  D1 as base64 text (600 KB of JPEG at most, far under D1's 2 MB row limit) and served at
  `/photos/u/<id>.jpg` with an immutable cache; a new photo is a new id. The 18 first
  ones are static files in `photos/`, made by `npm run photo`, which does the same
  strip on a Mac.
- **Volume.** D1's free plan holds 500 MB per database; a photo is ~150-350 KB as text,
  so the limit is around 1,500 photos, and a photo is read from D1 once per device
  because the browser keeps it. A list of dozens per occasion is nowhere near; thousands
  of photos would be the point to move them to R2, which needs the account to enable it.

Behaviour and its tests: [`openspec/specs/wishlist/list/spec.md`](../../openspec/specs/wishlist/list/spec.md).

## Layout

```text
wishlist/
├── gifts.json            # The first list, the seed behind migrations/0003 (not the live list)
├── photos/               # Its 1280 px JPEGs without metadata, shipped as static assets
├── web/                  # The list page, the admin page, styles and scripts
├── assets/icon.svg       # Home-screen icon; web/ holds it as SVG and 180, 192, 512 px PNGs
├── assets/admin-icon.svg # The same gift in green with a tick, for the /admin shortcut
├── src/app.ts            # Routes, claims, Basic auth; src/worker.ts only exports it
├── src/gifts.ts          # The list in D1, and adding, editing, hiding, deleting, photos
├── src/jpeg.ts           # EXIF orientation, metadata stripping, the baseline rebuild; the
│                         #   Worker and scripts/photo.ts share it
├── src/http.ts           # Responses, the same-site check, security headers
├── migrations/           # D1 schema (0002) and the one-time import of gifts.json (0003)
├── scripts/build.ts      # Checks the seed and writes dist/ for the Worker
├── scripts/seed.ts       # Generates migrations/0003 from gifts.json
├── scripts/photo.ts      # Takes a photo into photos/: resize, upright, no metadata
├── scripts/set-admin.sh  # Sets the /admin credentials as Worker secrets
├── tests/                # Vitest; the Worker runs against Node's SQLite
├── wrangler.toml         # Worker, assets and D1 binding
└── deploy/               # Pinned wrangler, kept apart from the test install
```

## Commands

```bash
npm ci                                   # once
npm test && npm run typecheck            # what CI runs
npm run photo -- ~/Downloads/IMG_1234.jpg lego-fire-station   # a static photo (seed list only)
npm run build                            # check the seed, write dist/
npm run seed                             # regenerate migrations/0003 after editing gifts.json
npm run dev                              # local site with a local D1 at http://localhost:8787
npm run deploy                           # migrations + upload
npm run set-admin                        # once: /admin credentials (user "regalos"), password left on the clipboard
```

Day-to-day steps (adding gifts from the phone, a new occasion, fixing a claim) are in
[OPERATIONS.md](OPERATIONS.md).

## Icon

`assets/icon.svg` is the source. After changing it, render the PNGs with headless
Chrome at 180 (`web/apple-touch-icon.png`, iOS), 192 and 512 (`web/icon-*.png`, the
manifest for Android), and copy the SVG to `web/icon.svg`. `assets/admin-icon.svg` goes the same way to
`web/admin-touch-icon.png`, `web/admin-icon-*.png` and `web/admin-icon.svg`. Use a throwaway
`--user-data-dir` and a new file name each time, because Chrome caches a `file://`
image. A phone keeps the icon it saved, so the shortcut has to be added again.

What changed, release by release: [`release-notes.md`](release-notes.md).
