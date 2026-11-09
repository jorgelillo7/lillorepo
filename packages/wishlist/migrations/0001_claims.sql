-- One row per gift someone has claimed. A gift with no row is free. The primary key
-- is what makes a reservation atomic: a second claim on the same gift inserts nothing.
CREATE TABLE claims (
  gift_id TEXT PRIMARY KEY,
  name TEXT,
  token_hash TEXT NOT NULL,
  reserved_at TEXT NOT NULL,
  bought_at TEXT
);
