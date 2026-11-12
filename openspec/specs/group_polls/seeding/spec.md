# Capability: seeding

The public feed starts with questions the owner publishes in batches, so a new user
finds something to vote on.

- **Source:** `packages/group_polls/scripts/seeding.py` (the pure helpers) and
  `packages/group_polls/scripts/seed.py` (the command; a dry run unless `--publish N`)
- **Verified by:** `packages/group_polls/scripts/tests/test_seeding.py`

---

### Requirement: A seed question fits the rules before it is published

Every seed question SHALL fit the limits `poll-rules` enforces (question 5 to 120
characters, answers 1 to 30 and different ignoring case) in both Spanish and English,
and an invalid entry SHALL be reported by its position and language. A question the
rules would reject would fail halfway through a batch.

#### Scenario: validation
- **WHEN** the shipped question list is loaded
- **THEN** it loads without error, and no Spanish question repeats
- **WHEN** an entry has equal answers
- **THEN** the error names its index and language
- *Verifies:* `test_every_seed_question_fits_the_app_limits`, `test_invalid_entries_are_named`

#### Scenario: lengths outside the limits
- **WHEN** a question is shorter than 5 or longer than 120 characters, or an answer is empty or longer than 30, in Spanish or in English
- **THEN** the error names the index, the language and `question length` or `answer length`
- **WHEN** a question or an answer is exactly at a limit
- **THEN** it loads
- *Verifies:* `test_lengths_outside_the_limits_are_named`, `test_lengths_at_the_limits_are_accepted`

### Requirement: Batches never repeat a question

The next batch SHALL be the first N questions, in file order, not published yet, so
running the script twice does not duplicate the feed.

#### Scenario: batches
- **WHEN** some questions are already published
- **THEN** the batch skips them and continues in order
- *Verifies:* `test_batches_skip_published_questions`

### Requirement: A seed poll is a valid public poll

A seed document SHALL match the schema the rules accept (public, 7 days, counters and
reports at zero, not hidden, the creator marked as the seed) under a fresh code from the
rules' alphabet. `createdAt` is set by the caller from the server's time.

#### Scenario: the document
- **WHEN** a poll document is built from a question
- **THEN** it has the schema's fields, starting values and a 12-character code
- *Verifies:* `test_documents_match_the_app_schema`
