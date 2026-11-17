-- What kind of toy a gift is, for the list's third filter. One of the ids in
-- CATEGORIES (src/gifts.ts); NULL shows the gift under "Todos" only.
ALTER TABLE gifts ADD COLUMN category TEXT;
