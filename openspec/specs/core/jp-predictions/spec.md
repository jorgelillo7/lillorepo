# Capability: jp-predictions

Reads the full LaLiga player list with next-matchday projections from Jornada
Perfecta's private mobile API. It is the only source a decision reads for
availability and projected points.

- **Source:** `core/sdk/jp.py`
- **Verified by:** `core/tests/test_jp.py`

---

### Requirement: A masked auth failure is an error, not an empty league

`fetch_all_players` SHALL raise `RuntimeError` when JP answers 200 with no
`players`. The message SHALL say the token has probably rotated and how to
extract a new one from the app's bundle. A non-2xx status escapes from it as
`requests.HTTPError`. `check_api_health` SHALL raise `RuntimeError` in every
failure case: a non-200, an empty payload, or JP being unreachable.

JP answers a rotated or invalid token with HTTP 200 and `{"error": "auth"}`.
Checking the status alone would parse that as an empty league, and the digest
would run on no data. The token lives in the mobile app's JS bundle, so the
fix is always the same extraction, and the error carries it. The health probe
wraps everything in `RuntimeError` so the orchestrator's top-level handler has
one well-known type to catch.

#### Scenario: auth error, empty payload, HTTP error, network error
- **WHEN** JP returns 200 with `{"error": "auth"}` **THEN** `fetch_all_players`
  raises "token posiblemente rotado"
- **WHEN** the health probe sees an empty `players` or an HTTP 403 **THEN** it
  raises `RuntimeError`
- **WHEN** the health probe cannot reach JP **THEN** it raises "JP API
  unreachable"
- **WHEN** JP answers with players **THEN** the health probe passes
- *Verifies:* `test_fetch_all_players_raises_on_auth_error_masked_as_200`,
  `test_check_api_health_raises_on_empty_players`,
  `test_check_api_health_raises_on_http_error`,
  `test_check_api_health_wraps_connection_error`,
  `test_check_api_health_passes_on_success`

> **GAP — unverified.** Nothing asserts what `fetch_all_players` raises on a
> non-2xx or a network error: it lets `requests` exceptions escape, unlike the
> health probe. A test would mock a 500 and pin the type. Whether it should
> wrap them like `check_api_health` is an open question, not a requirement.
> Candidate for the next test-hardening pass.

### Requirement: Re-fetch only when JP has refreshed

A cold call SHALL fetch the whole list (`limit=600`). A warm call SHALL first
send a `limit=5` probe and return the cached list when the highest
`updated_at` in the probe sample matches the cached fingerprint. It SHALL
re-fetch when the fingerprint moves. Players in the sample with no
`updated_at` SHALL be ignored when computing the fingerprint. The cache is per
process and keyed by competition and scoring type.

JP rewrites all ~549 players over a batch window of a few minutes, so each
player carries its own timestamp. The maximum across a sample is a stable
fingerprint of the snapshot. Reading a single player was not: its position in
`priceIncrement DESC` shifts between requests. The probe costs about 200 ms,
while a full fetch costs seconds.

#### Scenario: cold fetch, warm hit, refresh, gap in sample
- **WHEN** the cache is cold **THEN** one full request is sent, carrying the
  token and `showPredict=true`
- **WHEN** the probe's fingerprint is unchanged **THEN** the cached list is
  returned after one `limit=5` call
- **WHEN** any player in the sample has a newer `updated_at` **THEN** the full
  list is fetched again
- **WHEN** one sampled player has no projection **THEN** the fingerprint uses
  the others and the cache still hits
- *Verifies:* `test_fetch_all_players_returns_list`,
  `test_fetch_all_players_uses_cache_when_fingerprint_unchanged`,
  `test_fetch_all_players_invalidates_when_any_top_player_refreshes`,
  `test_fetch_all_players_probe_resilient_to_player_without_timestamp`

> **GAP — unverified.** A failed probe (network error, auth error, no
> timestamps) with a warm cache is meant to fall through to the full fetch,
> which then raises loudly. Nothing exercises that path. A test would warm the
> cache, make the `limit=5` request fail, and assert that a full request
> follows. Candidate for the next test-hardening pass.

### Requirement: No projection is one state, read in one place

`get_predict_rate(player, score_type)` SHALL return the `rate` for the
requested scoring type. It SHALL return `None` when the player is `None`, when
the player has no `predict` entries, or when the requested type is absent.

A Biwenger player JP has not listed yet reaches this function as `None`. That
is a normal state, not a caller error, and it means the same as a player with
no scheduled match: no projection. Nine of the ten call sites guarded for it
and the tenth did not, which took the league ranking down. The guard lives
here, once.

#### Scenario: rate found, missing, no player
- **WHEN** the player has the requested type **THEN** its rate is returned
- **WHEN** `predict` is empty, missing or lacks the type **THEN** `None`
- **WHEN** the player itself is `None` **THEN** `None`
- *Verifies:* `test_get_predict_rate_returns_value`,
  `test_get_predict_rate_returns_none_when_missing`,
  `test_get_predict_rate_treats_a_missing_player_as_no_projection`
