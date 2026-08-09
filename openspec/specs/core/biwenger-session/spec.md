# Capability: biwenger-session

Log in to Biwenger's private API and pin the session to one league, so every
later call is made as a known user inside a known league.

- **Source:** `core/sdk/biwenger.py` (`BiwengerClient.__init__`,
  `_authenticate`)
- **Verified by:** `core/tests/test_biwenger_client.py`

---

### Requirement: A client either holds a usable session or does not exist

Construction SHALL authenticate: POST the credentials, keep the returned bearer
token on the session, read `/account`, resolve the caller's `user_id` **for the
requested league**, and pin `X-League` / `X-User` onto every later request.

There is no unauthenticated client state, because every read and every write
below assumes both are set. Two answers arrive with HTTP 200 and are still
unusable, and both SHALL raise `BiwengerError`:

- a login response carrying no `token` — the session would go out unauthenticated;
- an account response whose leagues do not include the requested one — the
  session would go out unpinned, and Biwenger answers an unpinned request with
  plausible-looking data for a different league, which is worse than an error.

#### Scenario: a constructed client is authenticated and pinned
- **WHEN** construction succeeds
- **THEN** `user_id` is the id Biwenger reports for that league, and the session
  carries `X-League` and `X-User`
- *Verifies:* `test_authentication_success`

#### Scenario: construction refuses a session it cannot use
- **WHEN** the login answer has no token
- **THEN** it raises rather than returning a half-built client
- **WHEN** the account answer does not contain the requested league
- **THEN** it raises
- *Verifies:* `test_authentication_raises_when_login_returns_no_token`,
  `test_authentication_raises_when_user_not_in_league`

### Requirement: A refusal and a broken connection are different types

A well-formed but unusable answer SHALL raise `BiwengerError`; transport
failures SHALL stay `requests` exceptions.

The distinction is what makes retrying decidable. `BiwengerError` means
Biwenger understood and said no — a bad password or a league the account is not
in never recovers on a second attempt. A connection reset might. Collapsing
both into one type would make every login failure look retryable to
[`http-retry`](../http-retry/spec.md) and to every caller that catches around
an SDK call.

#### Scenario: a refusal is typed as one
- **WHEN** Biwenger answers 200 with an unusable body
- **THEN** the caller sees `BiwengerError`, not an `HTTPError` and not an
  `AttributeError` from a missing key
- *Verifies:* `test_authentication_raises_when_login_returns_no_token`,
  `test_authentication_raises_when_user_not_in_league`

### Requirement: The session presents itself as Biwenger's own web client

Every request SHALL carry the browser identity the Biwenger web app sends: a
desktop `User-Agent`, `X-Lang`, and a pinned `X-Version`. They are set on the
login POST and merged into the session, so they travel with the bearer token on
every later call.

The API is private and undocumented; these headers were transcribed from the
web app's traffic, not from a contract. That is also their weakness — nothing
here records which of them Biwenger actually enforces, and `X-Version` pins a
web-app build that the live app moves past.

> **GAP — unverified.** No test asserts the identity headers survive onto the
> session alongside `Authorization`, and nothing observes what Biwenger does
> with a stale `X-Version` — that answer can only come from the wild. A test
> could at least pin the merge: after construction, the session carries the
> bearer token *and* the three identity headers.

### Requirement: Opening a session costs two Biwenger requests

Constructing a client SHALL perform exactly one login POST and one `/account`
GET.

Biwenger rate-limits per account, not per league or per caller — the quota read
off a `429` is 500 requests in a rolling 8-hour window, shared by the daily
digest, the bot and the draft. A caller that builds a client per operation
spends two of those before doing any work, which is what made a 105-pick draft
cost roughly three requests per pick. Holding one client for the life of a run
is therefore a caller obligation this SDK cannot enforce, only make cheap to
honour.

> **GAP — unverified.** Nothing asserts the request count of construction, and
> nothing in `core` guards against a caller re-authenticating in a loop. A test
> would assert two HTTP calls for one constructor.
