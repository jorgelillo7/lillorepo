# Capability: moderation

The owner reviews the public polls that users reported or that the rules hid, from a
command-line queue, because the app has no moderator screen.

- **Source:** `packages/group_polls/scripts/moderation.py` (the pure helpers) and
  `packages/group_polls/scripts/moderate.py` (the command)
- **Verified by:** `packages/group_polls/scripts/tests/` (the pure helpers and the command)

---

### Requirement: Reported or hidden polls are in the queue, most reported first

A poll SHALL need review when it is hidden or has at least one report, and the queue
SHALL list those codes with the most reported first, so the worst case is read first.
The threshold that hides a poll lives in the rules and the app; the script's copy must
match.

#### Scenario: the queue
- **WHEN** polls are clean, reported or hidden
- **THEN** only the reported and hidden ones are listed, ordered by reports descending
- *Verifies:* `test_reported_or_hidden_polls_need_review`, `test_queue_puts_the_most_reported_first`

### Requirement: Each poll is one readable line

A poll's summary SHALL show its state (hidden or visible), reports, votes, age, creator
(or "anonymous") and id, visibility and language, then the question and both answers,
so a decision needs no other screen.

#### Scenario: the summary
- **WHEN** a poll is summarised
- **THEN** the line carries state, votes, age and creator name
- *Verifies:* `test_summary_shows_state_votes_age_and_creator`

### Requirement: Restore and remove ask first and touch only that poll

`restore` SHALL make the poll visible and clear its reports, and `remove` SHALL delete
the poll with its votes and its reports, each only after the owner answers `y`; any other
answer, or no answer, SHALL write nothing. A code with no poll SHALL be reported without
asking.

#### Scenario: restore and remove
- **WHEN** `restore` is confirmed
- **THEN** the poll is not hidden, has 0 reports and no report documents, and its votes and other polls are untouched
- **WHEN** `remove` is confirmed
- **THEN** the poll, its votes and its reports are gone and other polls are untouched
- **WHEN** the answer is empty, `n`, anything but `y`, or the input ends
- **THEN** nothing is written
- **WHEN** the code matches no poll
- **THEN** the command exits 1 without a prompt or a write
- *Verifies:* `test_restore_unhides_the_poll_and_clears_only_its_reports`, `test_remove_deletes_the_poll_with_its_votes_and_reports`, `test_nothing_is_written_unless_the_answer_is_y`, `test_an_unknown_poll_is_reported_and_never_prompts`
