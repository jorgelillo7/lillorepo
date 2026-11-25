# Capability: identity-and-moderation

Who the visitor is and what they may do: a nickname anyone can claim until a
Google account links it, an optional Google identity that also confers admin,
and the moderation surface that blocks an abusive contributor.

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

### Requirement: A linked nickname belongs to its Google account

A nickname whose user document carries `google_email` SHALL NOT be claimable by
typing it: `/login` SHALL refuse it, set no session, and say on the next page
that the nickname is linked and Google is the way in.

Typing is the whole of a nickname's protection, which is fine for a nickname
nobody cares about and not for one with years of favourites and contributions,
or an admin's. Linking is how an owner opts out of that: unlinked nicknames keep
working exactly as before, so nobody is forced through Google.

#### Scenario: the typed claim is refused
- **WHEN** a linked nickname is posted to `/login` **THEN** no session is set
  and the following page names the nickname and points to the Google button
- *Verifies:* `test_a_linked_nickname_cannot_be_typed`,
  `test_the_refusal_says_to_use_google`

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

### Requirement: A Google credential is verified, and picks the nickname

`/auth/google` SHALL verify the GIS credential's signature and audience against
`GOOGLE_CLIENT_ID`, require `email_verified`, and store the email and name in
the session. The nickname SHALL then be, in order:

1. the one already **linked** to that email (`google_email` on the user);
2. else the nickname in the session, if it is not linked to another account,
   which this sign-in **links** to the email;
3. else one **derived** from the email's local part (lowercased,
   non-`[a-z0-9_-]` folded to `-`, capped at 20 chars), skipping any nickname
   another Google account owns by adding `-2`, `-3`…, and linked to the email.

A blocked nickname SHALL get no session nickname, whichever way it was reached.

Order 1 is what makes linking stick: signing in with Google alone returns the
owner to their own nickname instead of minting a second account. Order 2 is how
an owner links: type the nickname once, then Google. The first Google account
to do that owns an unlinked nickname, which is the same trust typing it already
gave; a linked one is never taken. The derivation exists so signing in is enough
to favourite and contribute without inventing a nickname.

Because the GIS script mints the POST itself and cannot read our form token,
this route SHALL verify Google's double-submit cookie (`g_csrf_token` in body
and cookie must match) **instead of** the session CSRF token, and reject a
mismatch with 403.

#### Scenario: sign-in, derivation, and the cookie check
- **WHEN** a valid credential arrives **THEN** the email and name land in the
  session and `maria.perez@example.com` becomes nickname `maria-perez`
- **WHEN** a session holding `jorgelillo` signs in with Google **THEN**
  `jorgelillo` is linked to that email and stays the nickname
- **WHEN** a linked account signs in with Google alone **THEN** it gets its
  linked nickname and no derived account is created
- **WHEN** the derived nickname is linked to another account **THEN** the
  sign-in gets `maria-2` and the other link is untouched
- **WHEN** the session's nickname is unlinked and another account owns a
  different one **THEN** only the session's nickname is linked
- **WHEN** the linked nickname is blocked **THEN** no nickname is set
- **WHEN** the body and cookie `g_csrf_token` disagree **THEN** 403
- *Verifies:* `test_google_login_sets_identity_and_derives_nickname`,
  `test_google_login_rejects_csrf_cookie_mismatch`,
  `test_google_after_a_nickname_links_that_nickname`,
  `test_google_alone_comes_back_to_the_linked_nickname`,
  `test_google_never_takes_a_nickname_linked_to_another_account`,
  `test_a_typed_nickname_linked_to_someone_else_is_not_claimed`,
  `test_a_blocked_linked_nickname_gets_no_session`

### Requirement: Admin is a Google-verified email, never a nickname

`is_admin` SHALL be true only for a session whose **Google** email is in
`ADMIN_EMAILS`. `/admin` and `/admin/bloquear/<nickname>` SHALL answer 403 to a
signed-out visitor and to a signed-in non-admin.

A nickname is self-asserted, so nickname-based admin would be admin by typing.
The paid studio photo follows the same rule: only a session with a verified
Google admin identity may use it, and while Sign-In is unconfigured nobody can,
so the studio is off for everyone.

#### Scenario: the admin gate
- **WHEN** signed out, or signed in with a non-admin email **THEN** 403
- **WHEN** signed in with an admin email **THEN** the users table renders
- *Verifies:* `test_admin_page_requires_admin_email`

#### Scenario: the studio gate
- **WHEN** Sign-In is unconfigured, whatever the nickname **THEN** the studio is not called
- **WHEN** Sign-In is configured and the session has an admin Google email
  **THEN** the studio is called
- **WHEN** the Google email is not an admin's **THEN** it is not
- *Verifies:* `test_a_typed_nickname_never_reaches_the_studio`,
  `test_a_google_admin_gets_the_studio_once_sign_in_exists`,
  `test_a_google_account_that_is_not_an_admin_does_not`

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
  ask what the label said, so it must be undoable by `packages/be_water/scripts/revert_water.py`;
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
