# Capability: daily-digest

The 09:00 Madrid cron orchestration (`POST /digests/daily`): send the squad +
market images to Telegram, then chain the lineup, auto-bid, a warning when a
clause protection is about to end (`league-cash` spec) and any offer worth
accepting. This is
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
squad → market → lineup → bids. It then chains the offers inbox, accept-only,
after auto-bid.

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

### Requirement: The morning interrupts only for what needs acting on

`run_daily` SHALL NOT send the league's squad values, and SHALL send an offer
only when it is scored ACEPTAR — no DUDOSO, no "descartadas" summary.

Both are available on demand (`/comparar`, `/ofertas`), and a briefing that
arrives with six to eight messages every morning trains its reader to skim
past the one that matters. The squad values also cost a squad read per
manager for a number that barely moves from one day to the next.

#### Scenario: a quieter morning
- **WHEN** the digest runs **THEN** no league value ranking is built or sent
- **WHEN** the offers step runs **THEN** it asks for accept-only mode
- *Verifies:* `test_run_daily_sends_no_league_value_snapshot`,
  `test_run_daily_chains_offers_inbox_after_auto_bid`

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

The second opinion SHALL be the most expendable step of all. `build_context`
reads Oráculo once per request and SHALL degrade to Jornada Perfecta alone on
any failure — the index comes back empty, `oraculo_ok` false, and every reader
already treats an empty index as "no opinion on anybody".

The same read also derives `oraculo_scale`, the JP/Oráculo percentile map,
once from the whole `biwenger_players` population
(`custom_prediction.global_scale`) — never per table. It shares the index's
fallback exactly: there is no state where the index survives a failure but
the scale does not, or the reverse. Every reader that threads the index
through to a row builder threads `oraculo_scale` alongside it, so the same
player blends to the same number wherever this context's rows end up
rendered.

The catch there is deliberately broad rather than typed to `OraculoError`.
Oráculo is read out of a page we do not control, so the likely failure is a
shape change surfacing as `KeyError` or `TypeError`, not the network error the
SDK raises. Catching only the typed one would take the 09:00 digest down for a
source the design calls optional.

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

#### Scenario: the second opinion is unreachable, or unreadable
- **WHEN** the Oráculo read raises the SDK's own error, from either endpoint
- **THEN** the context carries an empty index, `oraculo_scale` is `None`,
  `oraculo_ok` is false, and `build_context` returns normally
- **WHEN** it raises something the SDK never declared, as a shape change would
- **THEN** the same, rather than propagating into the digest
- **WHEN** the index reads fine but deriving the scale from it raises
- **THEN** the same degradation, not a half-broken context with an index and
  no scale
- *Verifies:* `test_an_oraculo_error_leaves_the_index_empty_and_does_not_raise`,
  `test_an_oraculo_error_from_predictions_is_caught_too`,
  `test_a_shape_change_at_the_provider_is_caught_too`,
  `test_a_failing_global_scale_degrades_to_jp_alone_without_raising`

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
