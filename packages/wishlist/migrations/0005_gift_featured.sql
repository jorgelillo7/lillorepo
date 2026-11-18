-- A starred gift is one of the children's favourites: it goes first in every filter.
ALTER TABLE gifts ADD COLUMN featured INTEGER NOT NULL DEFAULT 0;
