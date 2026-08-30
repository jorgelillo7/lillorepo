# Capability: identity-and-moderation

Who the visitor is and what they may do: a nickname anyone can claim, an
optional Google identity that also confers admin, and the moderation surface
that blocks an abusive contributor.

The catalogue is public and readable by anyone — identity buys favourites, the
right to add a water, and nothing else. Admin is a separate, stricter claim.

- **Source:** `packages/be_water/web/auth.py`,
  `packages/be_water/web/routes/session.py`,
  `packages/be_water/web/routes/admin.py`,
  `packages/be_water/web/helpers.py` (`is_admin`, `nickname_blocked`, limiters)
- **Verified by:** `packages/be_water/web/tests/test_routes.py`

---

### Requirement: Reading never requires an identity

Every catalogue surface SHALL answer an anonymous visitor with the content, not
a login wall. Signing in SHALL only add favourites, contribution and admin.

A water nobody can read without an account is a water search engines cannot
index and a stranger cannot be shown, which defeats the point of the catalogue.

#### Scenario: anonymous browsing
- **WHEN** a visitor with no session opens the catalogue
- **THEN** the waters are rendered
- *Verifies:* `test_an_anonymous_visitor_gets_the_waters_not_a_login_wall`

### Requirement: A nickname is claimed, not registered

`/login` SHALL accept a nickname matching `NICKNAME_RE` (2–20 chars,
`[a-zA-Z0-9_-]`), lowercase it, record the visit, and put it in the session.
Anything else SHALL redirect back without a session.

There is no password because there is nothing to protect: a nickname owns
favourites and attribution, and the cost of impersonating one is the value of
having done so. Requiring an account would cost contributions the catalogue
needs more.

#### Scenario: valid and invalid nicknames
- **WHEN** a valid nickname is posted **THEN** the session carries it and the
  user's `last_seen` is touched
- **WHEN** the nickname fails the pattern **THEN** no session is set
- *Verifies:* `test_login_sets_session_and_favorite_toggles`,
  `test_login_rejects_bad_nickname`, `test_login_touches_last_seen`

### Requirement: Google Sign-In does not exist until it is configured

`/auth/google` and `/admin` SHALL answer **404** while `GOOGLE_CLIENT_ID` is
unset, rather than 403 or a broken button.

An endpoint that answers 403 advertises that it exists and invites attempts. An
unconfigured deployment has no admins at all, so the honest answer is that the
surface is not there.

#### Scenario: unconfigured deployment
- **WHEN** Sign-In is not configured **THEN** `POST /auth/google` and
  `GET /admin` are both 404
- *Verifies:* `test_google_routes_hidden_until_configured`

### Requirement: A Google credential is verified, and doubles as a nickname

`/auth/google` SHALL verify the GIS credential's signature and audience against
`GOOGLE_CLIENT_ID`, require `email_verified`, and store the email and name in
the session. When the visitor has no nickname yet, one SHALL be derived from
the email's local part (lowercased, non-`[a-z0-9_-]` folded to `-`, capped at
20 chars), unless that nickname is blocked.

The derivation exists so signing in is enough to favourite and contribute:
asking a signed-in user to also invent a nickname is a second gate for the same
person.

Because the GIS script mints the POST itself and cannot read our form token,
this route SHALL verify Google's double-submit cookie (`g_csrf_token` in body
and cookie must match) **instead of** the session CSRF token, and reject a
mismatch with 403.

#### Scenario: sign-in, derivation, and the cookie check
- **WHEN** a valid credential arrives **THEN** the email and name land in the
  session and `maria.perez@example.com` becomes nickname `maria-perez`
- **WHEN** the body and cookie `g_csrf_token` disagree **THEN** 403
- *Verifies:* `test_google_login_sets_identity_and_derives_nickname`,
  `test_google_login_rejects_csrf_cookie_mismatch`

### Requirement: Admin is a Google-verified email, never a nickname

`is_admin` SHALL be true only for a session whose **Google** email is in
`ADMIN_EMAILS`. `/admin` and `/admin/bloquear/<nickname>` SHALL answer 403 to a
signed-out visitor and to a signed-in non-admin.

A nickname is self-asserted, so nickname-based admin would be admin by typing.
`ADMIN_NICKNAMES` is a separate, weaker thing — it only gates who spends the
paid studio-photo call, never moderation.

#### Scenario: the admin gate
- **WHEN** signed out, or signed in with a non-admin email **THEN** 403
- **WHEN** signed in with an admin email **THEN** the users table renders
- *Verifies:* `test_admin_page_requires_admin_email`

### Requirement: Blocking stops contributing, retroactively

An admin SHALL be able to toggle `blocked` on a nickname. A blocked nickname
SHALL NOT be able to log in, and SHALL NOT be able to submit a water or a photo
even with a session obtained before the block.

Checking the flag only at login would leave an already-signed-in abuser working
until they logged out, which is exactly when the block matters.

#### Scenario: toggle, then refuse
- **WHEN** an admin posts the block toggle **THEN** the flag flips
- **WHEN** a blocked nickname logs in **THEN** no session is recorded
- **WHEN** a blocked nickname posts a water **THEN** nothing is saved
- *Verifies:* `test_admin_block_toggle_and_blocked_login`,
  `test_blocked_nickname_cannot_login_or_add`

### Requirement: The admin page surfaces stranded photos

The admin page SHALL list waters whose `photo_promotion_failed` flag is set,
alongside the users table.

The flag is written when a save cannot move a photo out of `uploads/`, and that
prefix is swept on a lifecycle rule: the ficha works for weeks and then does
not. Nothing read the flag, which made it an alarm with no bell.

> **GAP — unverified.** No test asserts that a water with
> `photo_promotion_failed` appears on the admin page. A test would set the flag
> on a catalogue water, sign in as an admin, and assert the id renders.

### Requirement: State-changing posts carry a CSRF token and a rate limit

Every state-changing route SHALL reject a request with no valid session CSRF
token (the Google callback excepted, above), and SHALL be bounded per client
IP: `LOGIN_LIMITER` 20/5 min, `SAVE_LIMITER` 30/h, `PHOTO_LIMITER` 15/h.

The photo limit is also a spend cap: every upload fires Gemini calls, which are
the only paid calls in the project.

#### Scenario: missing token, and too many photos
- **WHEN** `/login` or `/anadir` is posted without a token **THEN** it is
  refused and nothing is written
- **WHEN** the photo limit is exceeded **THEN** the upload is refused with a
  message rather than processed
- *Verifies:* `test_login_rejected_without_csrf`,
  `test_add_water_rejected_without_csrf`, `test_photo_uploads_are_rate_limited`

### Requirement: Signing out drops both identities

`/logout` SHALL clear the nickname and the Google identity from the session,
and SHALL do so only with a valid CSRF token.

Clearing one and not the other would leave a visitor who believes they left
still holding admin.

> **GAP — unverified.** No test posts `/logout` and asserts the session is
> empty. A test would sign in both ways, post `/logout`, and assert `nickname`,
> `google_email` and `google_name` are all gone.
