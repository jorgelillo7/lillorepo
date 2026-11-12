# Capability: poll-rules

The Firestore security rules of "¿Qué votáis?". The Android app talks to Firestore
directly, so these rules are the only boundary between users and the data: every
invariant of a poll, a vote and a report is enforced here.

- **Source:** `packages/group_polls/firestore.rules`
- **Verified by:** `packages/group_polls/tests/test_rules.py`, which runs the rules
  against the Firestore emulator and is skipped when `FIRESTORE_EMULATOR_HOST` is
  unset, as in CI; it is run by hand (`OPERATIONS.md`).

---

### Requirement: A poll is created whole and clean

A signed-in user SHALL create a poll under a 12-character code drawn from the
unambiguous alphabet (no `o`, `O`, `0`, `1`, `l`, `I`), with exactly the fields of the
schema, and as themselves. Its question SHALL be 5 to 120 characters, each answer 1 to
30 and different ignoring case, its duration 1, 7 or 0 (no limit) days, its time the
server's, and its counters, reports, `hidden` and `closedAt` at their starting values.
For a private poll the code is the only key to it, so it must not be guessable; and a
poll that starts with votes, reports or a hidden flag, or is backdated, would skip the
rules that earn those.

#### Scenario: valid and invalid polls
- **WHEN** a user creates a well-formed poll
- **THEN** it is accepted
- **WHEN** it names another creator, starts with votes, has a 3-day duration, starts hidden, has a too-short question, equal answers or a backdated time
- **THEN** it is rejected
- *Verifies:* `test_a_valid_poll_can_be_created`, `test_invalid_polls_are_rejected`

#### Scenario: codes
- **WHEN** a code is too short or uses an excluded character
- **THEN** the create is rejected
- *Verifies:* `test_codes_must_look_random`

### Requirement: Reading is limited to a code, the public feed and your own

Signed-out users SHALL read nothing. A signed-in user SHALL read any poll whose code
they know, and SHALL list only public polls or their own, so a query that does not
filter on one of the two is rejected. The vote of a user SHALL be readable by them;
everyone's votes SHALL be readable only on private polls, where results show who voted
what; a "delete my data" query by `voterId` across polls SHALL be allowed.

#### Scenario: reads
- **WHEN** a signed-out user reads a poll
- **THEN** it is refused, and a signed-in user holding a private poll's code can read it
- **WHEN** the feed query filters on `visibility == public`
- **THEN** it is allowed, while an unfiltered list of polls is refused and a query on one's own `creatorId` is allowed
- *Verifies:* `test_signed_out_users_cannot_read`, `test_feed_query_must_ask_for_public_polls`

#### Scenario: who voted
- **WHEN** another user lists the votes of a private poll
- **THEN** it is allowed; on a public poll it is refused, and only one's own vote is readable
- *Verifies:* `test_who_voted_is_readable_only_on_private_polls`

### Requirement: A vote is final, one per user, and counted with itself

A vote SHALL be created only by its own user, on an open poll, with a side and a
prediction, and in the same batch the poll's counter for that side SHALL go up by exactly
one. A second vote, a vote without its counter, a counter without its vote, the wrong
side's counter and a step of two SHALL be rejected. A vote SHALL carry a name only on a
private poll (up to 24 characters) and never on a public one. A poll is open until its
creator closes it or, unless it has no limit, its duration passes. Only the creator
SHALL close a poll.

#### Scenario: one vote with its counter
- **WHEN** a user votes with the counter incremented
- **THEN** the counter is 1, and voting again on the other side is rejected
- **WHEN** the vote and the counter are sent separately, with the wrong counter or with +2
- **THEN** the commit is rejected
- *Verifies:* `test_one_vote_with_its_counter`, `test_vote_and_counter_must_go_together`

#### Scenario: whose vote and which name
- **WHEN** a user votes as someone else
- **THEN** it is rejected
- **WHEN** a name is sent on a public poll
- **THEN** it is rejected, while on a private poll it is accepted
- *Verifies:* `test_cannot_vote_for_someone_else`, `test_names_only_on_private_polls`

#### Scenario: closed, expired and unlimited polls
- **WHEN** a poll is closed by its creator (and a non-creator's attempt to close it fails) or has outlived its duration
- **THEN** voting is rejected
- **WHEN** a poll with no limit is long past its creation
- **THEN** voting is still accepted
- *Verifies:* `test_no_votes_once_closed_or_expired`, `test_no_limit_polls_stay_open`

#### Scenario: the shape of a vote
- **WHEN** a vote has no `prediction`, or carries a field outside the allowed set, on a public or a private poll
- **THEN** the commit is rejected, and the same vote without the flaw is accepted
- **WHEN** a name on a private poll is 25 characters
- **THEN** it is rejected, while 24 characters are accepted
- *Verifies:* `test_a_vote_without_a_prediction_is_rejected`, `test_a_vote_with_an_extra_field_is_rejected`, `test_a_name_over_24_characters_is_rejected`

### Requirement: Polls are never deleted or rewritten

No poll and no vote SHALL be deleted, nobody SHALL lose their vote, and a poll SHALL
change only through the four allowed updates: a vote's counter, the creator closing it,
the creator blanking their own name, and a report. The question and the counters SHALL
not be editable directly.

#### Scenario: rewriting
- **WHEN** the creator changes the question or sets a counter to 100
- **THEN** the update is rejected
- *Verifies:* `test_polls_cannot_be_deleted_or_rewritten`

### Requirement: Three reports hide a public poll

A user other than the creator SHALL report a public poll once, in a batch that creates
their report and increases `reports` by one; the poll SHALL become hidden exactly when
`reports` reaches 3, in that same write. A private poll SHALL NOT be reportable and a
report SHALL NOT be readable or changed. The threshold is also in the moderation
script and the app, which must agree.

#### Scenario: reporting
- **WHEN** three different users report a public poll, each in a batch with the counter
- **THEN** the third batch is accepted only with `hidden` set, and the first two only without it; a second report by the same user is rejected
- *Verifies:* `test_three_reports_hide_a_public_poll`

#### Scenario: who can report what
- **WHEN** the creator reports their own poll, or anyone reports a private one
- **THEN** it is rejected
- *Verifies:* `test_only_others_report_and_only_public_polls`

### Requirement: "Delete my data" blanks names and keeps votes counted

A user SHALL be able to blank their own name on a vote or, as creator, on a poll,
and nothing else about it. The vote itself and its count SHALL stay.

#### Scenario: blanking
- **WHEN** a voter blanks their name on a private poll, or the creator blanks theirs
- **THEN** it is accepted, while changing the vote's side or blanking someone else's creator name is rejected
- *Verifies:* `test_delete_my_data_blanks_names_only`
