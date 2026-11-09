# wishlist — operations

## Add gifts

1. Take each photo in, with an id made of lowercase words joined by dashes:
   `npm run photo -- <image> <gift-id>`. It refuses to save a photo that still has
   metadata.
2. Add the gift to `gifts.json`: `id`, `for` (a recipient id: `older` or
   `younger`), `title`, the photo file name and, if useful, `detail` (brand, age,
   players) and `note` (which model, where and at what price it was seen).
3. `npm test && npm run build`. The build lists every problem in `gifts.json` at once.
4. Open a PR. After the merge, `npm run deploy` from `master`.

Removing a gift from `gifts.json` hides its claim; the row stays in D1 until a later
cleanup.

## A new occasion

Change `title` and `subtitle` and replace the gifts. Ids must not repeat an old gift's
id while its claim is still in D1, or the new gift starts out reserved. Clear the old
claims first:

```bash
deploy/node_modules/.bin/wrangler d1 execute wishlist --remote --command "DELETE FROM claims"
```

## Fix a claim

Open `/admin`. **Liberar** deletes the claim, so the gift is free again.
**Marcar comprado** marks a reserved gift bought, for a guest who bought it from
another phone.

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
