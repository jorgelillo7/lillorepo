# Capability: gifts

The list itself lives in D1, and the owner adds, edits, hides and deletes gifts, with a
photo from the phone, on `/admin`. A photo never keeps where it was taken.

- **Source:** `packages/wishlist/src/gifts.ts`, `packages/wishlist/src/jpeg.ts`,
  `packages/wishlist/src/app.ts`, `packages/wishlist/web/admin.js`,
  `packages/wishlist/migrations/`
- **Verified by:** `packages/wishlist/tests/*.test.ts` (Vitest; the Worker runs against
  Node's SQLite with every real migration). The page script, and the canvas resize in
  it, run in a browser and are not covered by the tests.

---

### Requirement: The public list is read from D1

`/api/list` SHALL return the current event's title, recipients and visible gifts in
order, each with the path of its photo. The first list SHALL be imported once with the
ids and static photo paths it had, so existing claims keep pointing at the same gifts.
Each gift SHALL belong to an event, and only the event marked current is shown.

#### Scenario: the imported list
- **WHEN** the migrations have run
- **THEN** the list has the title, recipients, gift ids and photo paths of `gifts.json`, in order, and no hidden flag
- *Verifies:* `gifts.test.ts: the first list is imported with its ids, recipients and static photos`

#### Scenario: claims survive
- **WHEN** a claim exists on an imported gift
- **THEN** `/admin` shows it with its name
- *Verifies:* `gifts.test.ts: existing claims survive the move to D1 and still show for the same ids`

### Requirement: Gifts are filed by kind for the list's third filter

A gift SHALL carry one category from a fixed list of six (coches, figuras, construir,
crear, musica, casa) or none; `/api/list` SHALL send that list with its labels and each
gift's category. Few on purpose, so the filter fits on a phone. Add and edit SHALL refuse
any other value; an edit that sends no category SHALL keep the gift's own, so an admin
page loaded before categories cannot wipe them. The public page SHALL offer the
categories as a "Tipo" filter between "Para" and "Estado", kept in the address as
`?tipo=`, listing only the kinds the chosen recipient has gifts of (plus the one
selected), with counts that apply the other two filters, and hidden when fewer than two
kinds are in use. A gift without a category shows only under "Todos".

#### Scenario: the list carries categories
- **WHEN** a gift is added with a category and another without
- **THEN** `/api/list` has the six categories in order, the first gift's category and `null` for the second
- *Verifies:* `gifts.test.ts: the list carries the categories, and each gift its own or none`

#### Scenario: unknown or missing category
- **WHEN** a gift is added or edited with a category outside the list, or edited without one, or with an empty one
- **THEN** the unknown one gets 400 `category`, the missing one keeps the gift's category, and the empty one clears it
- *Verifies:* `gifts.test.ts: an unknown category is refused on add and on edit, and an edit without one keeps it`

### Requirement: Starred gifts go first

The owner SHALL be able to star a gift on `/admin` as one of the children's favourites
and take the star off again. `/api/list` SHALL send `featured` for every gift and put the
starred ones first, then the rest in their own order, so every filter on the public
page shows the favourites first. The public card SHALL mark a starred gift
"★ Favorito", and the page header SHALL say what the star means.

#### Scenario: starring
- **WHEN** the last gift is starred, then unstarred, and an unknown gift or a non-boolean is sent
- **THEN** it comes first in the public and admin lists with `featured: true` while the others are `false`, the order goes back when the star comes off, and the bad requests get 400
- *Verifies:* `gifts.test.ts: a starred gift goes first on the list, and the star comes off again`

### Requirement: The owner adds a gift from the phone

A photo SHALL be uploaded first, as the raw `image/jpeg` body of `/admin/api/photo`,
and then named by the add request. A gift SHALL need a title, a photo uploaded and not
yet used, and a recipient of the event or none. Its id SHALL be made from the title
and kept unique. Text SHALL be collapsed and cut to its limit. An upload no gift took
SHALL be discarded after a day.

#### Scenario: adding
- **WHEN** a gift is added with a title, recipient, detail, note and uploaded photo
- **THEN** it takes the last place on the public list with those fields, and a second gift with the same title gets a different id
- *Verifies:* `gifts.test.ts: a new gift gets an id from its title, the last place, and shows on the public list`

#### Scenario: refusing
- **WHEN** the title is empty, the recipient unknown, or the photo missing, static or already in use
- **THEN** the request gets 400 and no gift is added
- *Verifies:* `gifts.test.ts: a gift needs a title, a known recipient and an uploaded photo nobody else uses`

#### Scenario: forgotten uploads
- **WHEN** an upload is more than a day old and no gift uses it, and another photo is uploaded
- **THEN** the old one is gone and photos in use are kept
- *Verifies:* `gifts.test.ts: an upload no gift took is discarded on the next upload after a day`

### Requirement: Photos carry nothing but the image

The admin page SHALL redraw a chosen photo through a canvas, at most 1280 px on its long
edge, before uploading it. The Worker SHALL independently rebuild every upload as a
single-scan baseline JPEG: keep only the tables, the frame, a colour profile and the
scan, cut everything after the end-of-image marker, and refuse a file that is not a
baseline JPEG, is wider or taller than 1600 px, would display turned by an EXIF
orientation that stripping drops, is truncated, or is larger than 600 KB. A photo
SHALL be served from `/photos/u/<id>.jpg` with an immutable cache, under an id that
changes whenever the photo does, and SHALL answer `HEAD` with the same headers. The seed
photos and the self-hosted font SHALL be cached for good too, since neither ever changes
under the same name; pages, scripts and styles SHALL keep the default revalidation.

#### Scenario: no metadata is stored
- **WHEN** a JPEG with EXIF and GPS, a multi-picture block, IPTC, a comment and a second EXIF-carrying picture appended after its end is uploaded
- **THEN** the stored bytes contain none of them, hold the image segments only and end at the first end-of-image marker
- *Verifies:* `gifts.test.ts: the stored bytes carry no EXIF, GPS, IPTC, comment or appended second picture`

#### Scenario: refused files
- **WHEN** the upload is not a JPEG, is progressive, too wide, turned by EXIF, over the cap, labelled as another type or truncated
- **THEN** it gets 400, 413 or 415 and nothing is stored
- *Verifies:* `gifts.test.ts: what is not a clean baseline JPEG, or is too big, is refused and nothing is stored`

#### Scenario: serving
- **WHEN** an uploaded photo is requested
- **THEN** it is served as `image/jpeg` with `Cache-Control: public, max-age=31536000, immutable`
- *Verifies:* `gifts.test.ts: an uploaded photo is served from D1 with an immutable cache and nothing but the image`

#### Scenario: HEAD
- **WHEN** an uploaded photo is requested with `HEAD`
- **THEN** it answers 200 with the same type and cache headers and no body
- *Verifies:* `gifts.test.ts: an uploaded photo answers HEAD with its headers and no body`

#### Scenario: static files
- **WHEN** a seed photo, the font, a page, a script or a stylesheet is requested
- **THEN** the seed photo and the font carry `Cache-Control: public, max-age=31536000, immutable`, and the rest carry none of their own
- *Verifies:* `gifts.test.ts: seed photos and the font are cached for good; pages and scripts are not`

### Requirement: Gifts can be edited, hidden and deleted

Editing SHALL change a gift's text, recipient and photo, and drop its old uploaded
photo. A hidden gift SHALL leave the public list and the public state, SHALL NOT be
reservable, and SHALL keep its claim for `/admin`. Deleting SHALL remove the gift, its
claim and its uploaded photo together, and a gift with a claim SHALL be deleted only
when the request says `force`, so a page that has not asked cannot delete it.

#### Scenario: editing
- **WHEN** a gift's text and photo are edited
- **THEN** the public list shows the change and the previous uploaded photo is gone
- *Verifies:* `gifts.test.ts: a gift's text and photo can change; the old uploaded photo goes`

#### Scenario: hiding
- **WHEN** a reserved gift is hidden
- **THEN** it leaves the public list and state, cannot be reserved, still shows in `/admin`, and comes back when shown again
- *Verifies:* `gifts.test.ts: a hidden gift leaves the public list and cannot be reserved, but keeps its claim`

#### Scenario: deleting
- **WHEN** a free gift is deleted, and when a claimed one is deleted without and then with `force`
- **THEN** the free one goes with its photo, the claimed one gets 409 and stays until forced, and then claim and photo go too
- *Verifies:* `gifts.test.ts: deleting removes the gift and its uploaded photo; a claimed gift needs force`
