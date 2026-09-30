## ADDED Requirements

### Requirement: A stable key for a board entry

`board_entry_key(entry)` SHALL return the same key for the same board entry on
every read, built from its type, date and what cannot change afterwards: the
ids of players and managers, amounts, clause values, bonus reasons, and for a
round its id and `scoreID`. Names, icons and article metadata SHALL NOT affect
it. `MONEY_ENTRY_TYPES` SHALL list the entry types that move money.

Board entries carry no id, and teams rename themselves, icons carry cache
busters and a round's article counts comments; a key over the whole payload
would duplicate the same movement across reads.

#### Scenario: same entry, different decoration; different entries, same second
- **WHEN** a team's name, an icon or a comment count changes between reads
  **THEN** the key does not
- **WHEN** two entries share a date **THEN** their keys differ
- **WHEN** a round is republished with a new `scoreID` **THEN** it keeps its
  own key
- *Verifies:* `test_board_entry_key_ignores_names_icons_and_comment_counts`,
  `test_board_entry_key_separates_entries_in_the_same_second`,
  `test_a_republished_round_keeps_its_own_key`
