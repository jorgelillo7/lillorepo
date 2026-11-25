-- One list for every occasion: the event carries its look, and a recipient can be
-- switched off (a birthday is one child's) without losing their gifts.
ALTER TABLE events ADD COLUMN theme TEXT NOT NULL DEFAULT 'navidad';
ALTER TABLE recipients ADD COLUMN active INTEGER NOT NULL DEFAULT 1;
