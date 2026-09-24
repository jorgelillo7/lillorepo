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

#### Scenario: a stranded photo is listed
- **WHEN** an admin opens the page and one water carries the flag **THEN** the
  "Fotos sin promover (1)" block names that water and no other
- *Verifies:* `test_admin_page_lists_the_stranded_photos`

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

#### Scenario: both identities go, and only with a token
- **WHEN** a signed-in admin posts `/logout` **THEN** `nickname`,
  `google_email` and `google_name` are all gone from the session
- **WHEN** it is posted without a valid token **THEN** the session is kept
- *Verifies:* `test_logout_drops_both_identities`,
  `test_logout_without_a_token_keeps_the_session`

### Requirement: An admin repairs a ficha's origin from the page, not the CLI

`/admin/agua/<id>` SHALL let a Google-verified admin edit a water's identity
and origin: name, brand, spring, retailer, country, province, community. It
SHALL 404 while Sign-In is unconfigured and 403 for a non-admin, like the rest
of the admin surface.

It SHALL NOT edit minerals. `data_audit.correct_field` owns those and they
carry a provenance this form has no way to ask about. What belongs here is what
no machine can recover: where the bottle is from.

Province, community and country SHALL be **selects** over
`geo.ALL_PROVINCES` / `ALL_COMMUNITIES` / `COUNTRY_CHOICES`. Free text is what
let `province='portugal'` and the `tramuntana` field shift reach Firestore; a
list cannot be mistyped. A stored value outside the list SHALL still be shown
and selected, so the ficha that needs repairing does not silently lose it on
first render.

The save SHALL:
- snapshot the previous document via `repository.save_revision` **before**
  overwriting — an admin edit is the one write with no contributor behind it to
  ask what the label said, so it must be undoable by `scripts/revert_water.py`;
- run `submission.resolve_place` with the submitted country, so an admin
  cannot hand-type a province/community mismatch the curation engine would then
  flag;
- leave every field the form does not carry untouched — minerals, photos,
  verification, authorship and the analysis series. An origin repair is not a
  re-submission.

#### Scenario: repairing the ficha that could not be repaired
- **WHEN** a non-admin opens it **THEN** 403
- **WHEN** an admin opens a flagged ficha **THEN** the geo reasons are shown
  beside selects carrying the canonical vocabularies
- **WHEN** the admin saves **THEN** a revision is stored first, keyed to their
  email, and the water is saved
- **WHEN** `Badajoz` is saved with community `Cataluña` **THEN** it becomes
  `Extremadura`
- **WHEN** the form omits minerals and verification **THEN** both survive
- **WHEN** the water does not exist **THEN** 404
- *Verifies:* `test_admin_edit_form_is_admin_only`,
  `test_admin_edit_form_offers_the_canonical_vocabularies`,
  `test_admin_edit_saves_a_snapshot_before_overwriting`,
  `test_admin_edit_applies_the_country_rules_on_save`,
  `test_admin_edit_keeps_what_the_form_does_not_carry`,
  `test_admin_edit_404s_on_a_water_that_does_not_exist`
