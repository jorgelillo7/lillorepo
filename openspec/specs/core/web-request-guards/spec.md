# Capability: web-request-guards

The basics every public Flask app in the repo needs behind Cloud Run: CSRF
protection on form POSTs, an abuse brake on public endpoints, and correct
absolute URLs behind the proxy that terminates TLS.

- **Source:** `core/web/csrf.py`, `core/web/ratelimit.py`, `core/web/proxy.py`
- **Verified by:** `core/tests/test_web.py`; the proxy fix through
  `packages/be_water/web/tests/test_routes.py`

---

### Requirement: Form POSTs carry a per-session CSRF token

`get_csrf_token()` SHALL return a random token stored in the signed session
cookie, created on first access and stable for the rest of the session.
`verify_csrf_token()` SHALL accept a POST only when the submitted `csrf_token`
form field matches the session's token, compared in constant time. It SHALL
reject the request when either side is missing.

A handful of admin and contribution forms do not justify Flask-WTF. The
session cookie is already signed, so it is a safe place for the token. The
constant-time comparison stops the token being guessed one character at a
time.

#### Scenario: stable token, reject missing or wrong, accept match
- **WHEN** the token is read twice in one session **THEN** it is the same
  value, at least 20 characters long
- **WHEN** the form carries no token, or one different from the session's
  **THEN** verification fails
- **WHEN** the form's token matches the session's **THEN** verification passes
- *Verifies:* `test_csrf_token_is_stable_per_session`,
  `test_verify_rejects_missing_and_wrong_token`,
  `test_verify_accepts_matching_token`

### Requirement: A sliding-window brake per key

`RateLimiter(max_events, window_seconds).allow(key)` SHALL allow at most
`max_events` attempts per key within any `window_seconds`, count keys
independently, and allow the key again once old attempts slide out of the
window. `reset()` SHALL clear every key.

This blunts bursts and simple bots at no cost. The state is deliberately per
Cloud Run instance, not shared: it is an abuse brake, not an accounting-grade
quota, and making it one would need a shared store the traffic does not
justify.

#### Scenario: block, independent keys, recover, reset
- **WHEN** a key exceeds `max_events` inside the window **THEN** `allow`
  returns False, while another key is still allowed
- **WHEN** the window slides past the old attempts **THEN** the key is allowed
  again
- **WHEN** `reset()` is called **THEN** a blocked key is allowed immediately
- *Verifies:* `test_rate_limiter_blocks_then_recovers`,
  `test_rate_limiter_reset`

### Requirement: Absolute URLs follow the forwarded scheme

`trust_proxy(app)` SHALL make the app honour `X-Forwarded-Proto` and
`X-Forwarded-Host` from exactly one upstream proxy. It SHALL NOT rewrite the
client address.

Cloud Run terminates TLS and forwards the original scheme, which Flask ignores
by default. Without this, every absolute URL comes out as `http://`: a sitemap
advertised 82 URLs that each answered with a redirect, and Google Sign-In
refuses an http redirect URI. Cloud Run is always the single proxy in front of
these services. The client IP is left alone because the rate limiters read
`X-Forwarded-For` themselves.

#### Scenario: https behind the proxy
- **WHEN** a request arrives with `X-Forwarded-Proto: https` **THEN** absolute
  URLs the app builds use `https://`
- *Verifies:* `test_absolute_urls_follow_the_forwarded_scheme`
