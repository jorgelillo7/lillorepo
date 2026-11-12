# Capability: moderation

The owner reviews the public polls that users reported or that the rules hid, from a
command-line queue, because the app has no moderator screen.

- **Source:** `packages/group_polls/scripts/moderation.py` (the pure helpers) and
  `packages/group_polls/scripts/moderate.py` (the command)
- **Verified by:** `packages/group_polls/scripts/tests/test_moderation.py`

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

> **GAP — unverified.** `moderate.py` itself (restore, remove, and the confirmation
> before deleting a poll with its votes and reports) talks to Firestore and has no test.
> A test would fake the client and assert what each command deletes or changes.
