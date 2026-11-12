# wishlist — operations

## Add gifts

From the phone, no Claude session or deploy involved: open `/admin` in Safari (a
normal tab, see the README on why not a web app), tap **Añadir regalo**, take or pick
a photo, fill the name and who it is for, and save. It is on the public list at once.
The same dialog edits a gift; **Ocultar** takes it off the public list without losing
reservations; **Borrar** removes the gift and its photo, and asks twice when someone
reserved it.

Rules the admin enforces: a photo of at most 600 KB after the page has resized it, a
name of at most 120 characters, detail 200, note 400. If a photo is refused, take
another; the page redraws it to 1280 px, so a refusal means the file was not a photo.

D1 is the source of truth for the list. `gifts.json`, `photos/` and
`migrations/0003_seed_gifts.sql` are the first Christmas list, imported once; changing
them does not change the site. After editing `gifts.json` for the repo's own sake, run
`npm run seed` (a test fails if the migration drifts from it).

## A new occasion

There is no admin screen for events yet. Add the event and its recipients in D1 and
switch `current`; the public list shows one event, and the old event's rows stay:

```bash
W=deploy/node_modules/.bin/wrangler
$W d1 execute wishlist --remote --command "UPDATE events SET current = 0; \
  INSERT INTO events (slug, title, subtitle, current) VALUES ('cumple-2027', 'Cumpleaños', NULL, 1); \
  INSERT INTO recipients (event, id, label, position) VALUES ('cumple-2027', 'older', 'Hermano mayor', 0)"
```

Per-event URLs and an admin screen are proposed in
`openspec/changes/wishlist-events/proposal.md`.
Claims belong to a gift, so a new event's gifts start free as long as their ids are new
(ids come from the title; the admin appends `-2` when one repeats).

## Fix a claim

Open `/admin`. **Liberar** deletes the claim, so the gift is free again.
**Marcar comprado** marks a reserved gift bought, for a guest who bought it from
another phone.

## Deploying

`npm run deploy` builds `dist/`, applies the pending D1 migrations to the remote
database (`0002` creates the tables, `0003` imports the first list and leaves the 18
claims and their ids untouched) and uploads the Worker. It is still manual, run from
`master` after a merge; nothing in CI deploys it. Migrations run once each, so a deploy
never reseeds over gifts added from the phone.

## First deploy on a Mac

```bash
npm --prefix deploy ci
deploy/node_modules/.bin/wrangler login
deploy/node_modules/.bin/wrangler d1 create wishlist   # once; put its id in wrangler.toml
npm run deploy
npm run set-admin
```

`npm run dev` reads the admin credentials from `.dev.vars` (gitignored):
`ADMIN_USER=...` and `ADMIN_PASSWORD=...` on two lines.
