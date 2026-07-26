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
running auto-bid exactly once, so the chat reads squad → market → bids. It then
chains the offers inbox after auto-bid. Missing Telegram credentials SHALL
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

### Requirement: A failing step never sinks the digest

An image failure SHALL fall back to a text note per-image and the digest SHALL
continue (mercado + auto-bid still run). A failure of one section's render
SHALL degrade only that section to a note. Auto-bid and offers failures SHALL
be swallowed into the summary (`error` key) while the route stays 200 OK. A
top-level failure SHALL send a Telegram alert before propagating — no silent
failures.

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

#### Scenario: top-level failure alerts
- **WHEN** the inner run raises (e.g. Biwenger 5xx during build_context)
- **THEN** a "Digest diario falló" Telegram message is sent before the error
  propagates
- *Verifies:* `test_run_daily_notifies_telegram_when_inner_raises`

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
