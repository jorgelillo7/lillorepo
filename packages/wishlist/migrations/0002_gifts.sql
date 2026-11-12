-- The list moves out of gifts.json into D1, so the owner can add gifts from a phone.
-- An event is one occasion's list; the public page shows the one marked current.
CREATE TABLE events (
  slug TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  subtitle TEXT,
  current INTEGER NOT NULL DEFAULT 0
);

-- Recipients are labels, never names: the list is public.
CREATE TABLE recipients (
  event TEXT NOT NULL,
  id TEXT NOT NULL,
  label TEXT NOT NULL,
  position INTEGER NOT NULL,
  PRIMARY KEY (event, id)
);

-- `photo` is a path on this site: /photos/<file> for a file shipped with the Worker,
-- /photos/u/<id>.jpg for one uploaded from /admin and kept in `photos`.
CREATE TABLE gifts (
  id TEXT PRIMARY KEY,
  event TEXT NOT NULL,
  recipient TEXT,
  title TEXT NOT NULL,
  detail TEXT,
  note TEXT,
  photo TEXT NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

-- An uploaded photo as base64 text: at most PHOTO_MAX_BYTES of JPEG, far under D1's
-- 2 MB row limit, and text comes back from D1 as a string in every environment.
CREATE TABLE photos (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
