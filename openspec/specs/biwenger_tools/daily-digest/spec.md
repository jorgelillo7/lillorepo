# Capability: daily-digest

The 09:00 Madrid cron orchestration (`POST /digests/daily`): send the squad +
market images to Telegram, then chain auto-bid and the offers inbox. This is
the capability the project SLO covers.

- **Source:** `packages/biwenger_tools/api/logic/digests.py`,
  `orchestration.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_digests.py`

---

### Requirement: End-to-end within the SLO

The daily digest SHALL complete end-to-end in ≤ 5 minutes wall-clock (the
project SLO). It chains: JP fetch + Biwenger session + market read + N bids +
Firestore log writes + 2 Telegram photos + 1 summary. Rationale, budget
breakdown and accepted gaps live in `CLAUDE.md` / `STATUS.md`.

### Requirement: Ordered sections, then bidding

`run_daily` SHALL send both images ("Mi equipo", then "Mercado") **before**
setting the lineup and running auto-bid exactly once, so the chat reads
squad → market → lineup → bids. It then chains the offers inbox after auto-bid.

The lineup step SHALL reuse the context the digest already built, so chaining it
costs no second JP + Biwenger round-trip, and SHALL be switchable off by
`DAILY_LINEUP_ENABLED` without a deploy — it writes to Biwenger every morning,
and a step that writes needs a switch that does not require a release. Missing Telegram credentials SHALL
short-circuit the whole run with `reason = telegram_credentials_missing` and no
sends.

#### Scenario: happy path ordering
- **WHEN** credentials are present and both images send
- **THEN** 2 images go out, then `run_auto_bid` is called once, then the
  offers inbox; the summary carries each step's result
- *Verifies:* `test_run_daily_chains_auto_bid_after_sending_images`,
  `test_run_daily_chains_offers_inbox_after_auto_bid`

#### Scenario: no credentials
- **WHEN** Telegram credentials are missing
- **THEN** nothing is sent and the result reason is
  `telegram_credentials_missing`
- *Verifies:* `test_run_daily_skips_send_when_telegram_creds_missing`

### Requirement: A daily photograph of what every squad is worth

`run_daily` SHALL send the league's squad values as a message **after** the
lineup, ranked and with the league total, and SHALL be switchable off by
`DAILY_LEAGUE_VALUES_ENABLED`.

Value only, no projection: projection changes every matchday and the lineup
message sent moments earlier already speaks to it, while value moves slowly and
is the number worth having a dated snapshot of. `/comparar` remains the on-
demand view that shows both.

It costs one squad read per manager on top of the digest, which is why it has a
switch — it is the first step to drop if the 09:00 budget gets tight. It runs
after the lineup because it answers a different question and must not be able
to disturb the one write of the morning.

An empty summary SHALL send nothing: a league read that comes back with no
managers means the fetch failed, not that everyone owns nothing.

#### Scenario: the snapshot goes out ranked
- **WHEN** the league summary has managers
- **THEN** one message ranks them by value and carries the league total
- *Verifies:* `test_run_daily_sends_the_league_value_snapshot`,
  `test_render_values_ranks_every_squad_and_totals_the_league`

#### Scenario: it cannot disturb the lineup
- **WHEN** the league read fails
- **THEN** the digest records the error and every other step stands
- *Verifies:* `test_the_league_value_step_cannot_break_the_lineup`

#### Scenario: a squad holding a player JP does not carry
- **WHEN** a manager owns a player with no Jornada Perfecta match
- **THEN** the squad is still measured — value from Biwenger alone, the
  missing projection counted as zero
- *Verifies:* `test_collect_survives_a_player_jornada_perfecta_does_not_carry`,
  `test_get_predict_rate_treats_a_missing_player_as_no_projection`

#### Scenario: nothing to rank, nothing sent
- **WHEN** the summary is empty
- **THEN** no ranking is sent and the reason is recorded
- *Verifies:* `test_an_empty_league_sends_no_ranking`

#### Scenario: switchable without a deploy
- **WHEN** `DAILY_LEAGUE_VALUES_ENABLED` is false
- **THEN** the step is skipped and no squad reads are paid for
- *Verifies:* `test_the_league_value_step_can_be_turned_off`

### Requirement: A squad image carries what the squad is worth

`build_table_image` SHALL add the summed cf-base price of its rows to the
header when asked, and SHALL NOT do so by default.

The same renderer draws the market, where the rows are other people's players
and a total would answer a question nobody asked. Squad views opt in: "Mi
equipo", each rival in `/analizar`, and the digest's team section.

The figure is the same cf-base price the Precio column shows and `/comparar`
ranks by, so the header and the table can never disagree.

#### Scenario: the total, and rows that lack a price
- **WHEN** rows carry prices **THEN** the header shows their sum
- **WHEN** a row has no price **THEN** it counts as zero rather than raising
- *Verifies:* `test_total_value_sums_the_cf_base_prices`,
  `test_total_value_keeps_one_decimal_when_there_is_one`,
  `test_total_value_survives_rows_without_a_price`,
  `test_build_table_image_renders_with_the_total_shown`

### Requirement: A failing step never sinks the digest

An image failure SHALL fall back to a text note per-image and the digest SHALL
continue (mercado + auto-bid still run). A failure of one section's render
SHALL degrade only that section to a note. Auto-bid and offers failures SHALL
be swallowed into the summary (`error` key) while the route stays 200 OK. A
top-level failure SHALL send a Telegram alert before propagating — no silent
failures.

A step that produces a **message of its own** SHALL also say in the chat that
it died, the way a dead image section does. Swallowing is about protecting the
rest of the digest, not about hiding: the league value step logged and said
nothing on its first real failure, and the silence read as a feature that had
never shipped.

#### Scenario: photo fails, digest continues (22–23/06 regression)
- **WHEN** both `sendPhoto` calls fail
- **THEN** each degrades to a text fallback, auto-bid still runs, `sent = 0`
- *Verifies:* `test_run_daily_continues_to_auto_bid_when_first_photo_fails`,
  `test_send_image_or_text_fallback_sends_text_on_telegram_delivery_error`

#### Scenario: one section render fails
- **WHEN** the "Mi equipo" render raises
- **THEN** only the market image is sent, the team section becomes a note,
  auto-bid still runs
- *Verifies:* `test_run_daily_market_survives_team_section_failure`

#### Scenario: downstream step fails
- **WHEN** auto-bid or the offers inbox raises
- **THEN** the error is captured in the summary and the digest is not lost
- *Verifies:* `test_run_daily_swallows_auto_bid_failure_and_still_returns_digest_summary`,
  `test_run_daily_swallows_offers_inbox_failure`

#### Scenario: a dead step is visible in the chat
- **WHEN** the league value step raises
- **THEN** the chat gets the same short note a dead image section gets, and
  every other step still runs
- *Verifies:* `test_a_failed_league_value_step_says_so_in_the_chat`,
  `test_the_league_value_step_cannot_break_the_lineup`

#### Scenario: top-level failure alerts
- **WHEN** the inner run raises (e.g. Biwenger 5xx during build_context)
- **THEN** a "Digest diario falló" Telegram message is sent before the error
  propagates
- *Verifies:* `test_run_daily_notifies_telegram_when_inner_raises`

### Requirement: The morning lineup is a floor, not the best one

Setting the lineup at 09:00 exists so a player who arrives overnight is fielded
without anyone opening the app. **One fixed hour is the deliberate choice**: the
alternative — waking near each kickoff — needs a tick that self-gates on the
fixture list, and the value of that over a floor plus a manual override does not
pay for the complexity. It SHALL NOT be treated as the optimal moment:
Biwenger locks each player at *his* own kickoff, and under the league's
"jornada única" configuration a matchday is not final until every match in it
has been played — 2026/27 opened with a round spanning twelve days. The manual
`/lineups/auto-pick` remains the way to re-align closer to a specific match —
and the point of the floor is that forgetting to do so costs a stale lineup
rather than an empty one.

#### Scenario: lineup step
- **WHEN** the digest runs and `DAILY_LINEUP_ENABLED` is on
- **THEN** the lineup is set from the digest's own context, before auto-bid
- **WHEN** it is off **THEN** the step is skipped and reported as `disabled`
- *Verifies:* operational switch, exercised by the digest's own chain

---

### Requirement: Config-driven auto-bid pause

While today is before `AUTO_BID_PAUSED_UNTIL` (an `YYYY-MM-DD` config value),
the digest SHALL skip bidding, post a pause note carrying the resume date, and
still run the offers analysis and send both images. A past or malformed date
SHALL leave bidding enabled — a typo must never silently disable it. No deploy
is needed to pause or resume.

#### Scenario: paused, expired, and malformed
- **WHEN** the date is in the future **THEN** auto-bid is skipped, a "pausadas"
  note with `/pujar` is posted, offers + images still run
- **WHEN** the date is past **THEN** bidding runs
- **WHEN** the date is malformed **THEN** bidding runs
- *Verifies:* `test_run_daily_skips_auto_bid_while_paused`,
  `test_run_daily_runs_auto_bid_once_pause_expired`,
  `test_run_daily_ignores_malformed_pause_date`
