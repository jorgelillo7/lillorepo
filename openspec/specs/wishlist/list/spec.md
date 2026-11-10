# Capability: list

A public gift list where each gift is claimed by one person at most, changed only from
the browser that claimed it, and whose claimers' names only the owner sees.

- **Source:** `packages/wishlist/src/app.ts`, `packages/wishlist/web/`,
  `packages/wishlist/scripts/build.ts`, `packages/wishlist/scripts/photo.ts`,
  `packages/wishlist/scripts/jpeg.ts`
- **Verified by:** `packages/wishlist/tests/*.test.ts` (Vitest; the Worker runs
  against Node's SQLite with the real migration)

---

### Requirement: A gift is claimed once

Reserving SHALL insert the claim only if the gift has none, in one statement, so two
people pressing at the same time cannot both get it. Only gifts on the list SHALL be
accepted, so the address cannot be used to fill the database.

#### Scenario: second claim
- **WHEN** a gift is already reserved and someone else reserves it
- **THEN** the second request gets 409 and the claim is unchanged
- *Verifies:* `worker.test.ts: a gift can be reserved once; a second visitor gets a conflict`

#### Scenario: unknown gift or foreign request
- **WHEN** the gift id is not on the list, the request comes from another origin, or it is not JSON
- **THEN** it is refused and nothing is stored
- *Verifies:* `worker.test.ts: a gift that is not on the list, or a request from another site, is refused`

### Requirement: Only the claimer changes a claim

The Worker SHALL give the claiming browser a random token in an HttpOnly, Secure,
SameSite=Strict cookie that outlives Safari's 7-day limit on script storage, and keep
only its hash. Marking bought and releasing SHALL need that token, and a bought gift
SHALL NOT be released by its claimer.

#### Scenario: marking bought
- **WHEN** a browser other than the claimer's marks the gift bought
- **THEN** it gets 403; the claimer's browser succeeds and the time of purchase is stored
- *Verifies:* `worker.test.ts: only the browser that reserved a gift can mark it bought, with the time`

#### Scenario: releasing
- **WHEN** someone releases a gift
- **THEN** only the claimer's browser can, the gift is free again, and a bought gift stays bought
- *Verifies:* `worker.test.ts: only the browser that reserved a gift can release it, and not once bought`

#### Scenario: the cookie
- **WHEN** a gift is reserved for the first time from a browser
- **THEN** the cookie is HttpOnly, Secure, SameSite=Strict, scoped to `/api` and lasts more than 300 days
- *Verifies:* `worker.test.ts: the token cookie is HttpOnly, scoped to the API and outlives Safari's 7 days`

### Requirement: Names are optional and private

The name SHALL be optional, with spaces collapsed and at most 40 characters. The
public state SHALL carry no names, only whether each claim is the viewer's own.

#### Scenario: public state
- **WHEN** anyone reads the state
- **THEN** each claim has its times and `mine`, and no name
- *Verifies:* `worker.test.ts: the state marks the visitor's own claims and never carries a name`

#### Scenario: the name
- **WHEN** a name is given
- **THEN** it is trimmed, collapsed and cut at 40 characters, and an empty one is stored as none
- *Verifies:* `worker.test.ts: the name is optional, trimmed and cut at the limit`

### Requirement: The owner sees names and fixes claims behind Basic auth

`/admin` and its API SHALL ask for the credentials stored as Worker secrets, compared in
constant time, and stay closed while those are unset. There the owner SHALL see names
and SHALL be able to release any claim or mark any reserved gift bought. Pages SHALL
be served only by their clean paths, so `admin.html` cannot be fetched around the check.

#### Scenario: no credentials
- **WHEN** `/admin` or its API is requested without the right credentials, or with the secrets unset
- **THEN** the answer is 401 with a Basic challenge and nothing is served
- *Verifies:* `worker.test.ts: asks for credentials, and stays closed while they are unset`

#### Scenario: with credentials
- **WHEN** the owner opens the admin API
- **THEN** names are shown, and any claim can be marked bought or released
- *Verifies:* `worker.test.ts: shows the names and can release or mark any claim`

#### Scenario: pages
- **WHEN** a page is requested by its `.html` path or an unknown API path is requested
- **THEN** the answer is 404, while `/admin.webmanifest` is served without credentials so a home-screen shortcut to `/admin` keeps its name, icon and start page
- *Verifies:* `worker.test.ts: serves the list and its files, the admin manifest without credentials, and no page by its .html path`

### Requirement: The list and its photos are safe to publish

The build SHALL refuse a list with a missing title, no gifts, a malformed or repeated
id, a gift without a title, a gift for someone not among the list's recipients, or a
photo that does not exist, and report every problem at once. Recipients are labels
such as "Hermano mayor", never names, because the site is public. A photo SHALL enter the repo upright, at most 1280 px, and without EXIF, XMP,
IPTC or comments, because phone photos carry where they were taken.

#### Scenario: the list in the repo
- **WHEN** the tests run
- **THEN** `gifts.json` has no problems
- *Verifies:* `build.test.ts: the list in the repo is valid`

#### Scenario: a broken list
- **WHEN** ids repeat or are malformed, a title is missing, a photo is missing, or the list is empty
- **THEN** each problem is reported
- *Verifies:* `build.test.ts: repeated ids, bad ids, missing titles and missing photos are all reported`,
  `build.test.ts: an empty list is refused`

#### Scenario: recipients
- **WHEN** a gift is for an id that is not among the recipients
- **THEN** the build reports it
- *Verifies:* `build.test.ts: a gift for someone not among the recipients is reported`

#### Scenario: photo metadata
- **WHEN** a photo is taken in
- **THEN** its orientation is read to turn it upright, and its metadata segments are dropped while the image is kept
- *Verifies:* `jpeg.test.ts: reads the EXIF orientation, and 1 when there is none`,
  `jpeg.test.ts: drops EXIF, GPS and comments and keeps the image segments`,
  `jpeg.test.ts: refuses what is not a JPEG`
