# Capability: seo

What Be Water hands a crawler or a link preview: absolute URLs, the canonical
form of each page, share metadata, and the structured data describing a water
and a region.

- **Source:** `packages/be_water/web/seo.py`, `packages/be_water/web/helpers.py`
  (`base_url`, `canonical_url`), `routes/main.py` (`robots`, `sitemap`),
  `core/web/proxy.py`, `templates/base.html`
- **Verified by:** `packages/be_water/web/tests/test_seo.py`,
  `packages/be_water/web/tests/test_routes.py`

---

### Requirement: Absolute URLs follow the forwarded scheme

Every absolute URL the app builds — sitemap entries, `robots.txt`, canonical
and `og:url` tags, `url_for(..., _external=True)` — SHALL use the scheme the
request actually arrived on. Cloud Run terminates TLS and forwards it in
`X-Forwarded-Proto`; Flask ignores that header unless told to trust it
(`core/web/proxy.trust_proxy`, scheme and host only, one hop).

Without it the sitemap advertised 82 `http://` URLs that each answered a 302,
and Google Sign-In — still to be activated — would have been handed an `http`
redirect URI it refuses.

When `BASE_URL` is set it wins, so mapping a public domain later is an
environment variable and not a code change.

#### Scenario: a forwarded https request yields https URLs
- **WHEN** the sitemap is fetched with `X-Forwarded-Proto: https`
- **THEN** every `<loc>` is `https://`, none is `http://`
- *Verifies:* `test_absolute_urls_follow_the_forwarded_scheme`

### Requirement: Canonical URLs drop reordering parameters

Every page SHALL declare `<link rel="canonical">` and `og:url`. The canonical
form SHALL omit parameters that reorder or filter a page without changing what
it is about — `perfil` (personalised vs neutral ordering) and `periodo` (the
community ranking window) — so the variants consolidate into one indexed page
instead of competing for the same content.

#### Scenario: the perfil toggle does not fork the page
- **WHEN** `/recomendar?lugar=Cuenca&perfil=0` is rendered
- **THEN** the canonical URL is `/recomendar?lugar=Cuenca`, with no `perfil`
- *Verifies:* `test_canonical_drops_the_parameters_that_only_reorder`,
  `test_every_public_page_declares_a_canonical_and_an_og_url`

### Requirement: robots.txt announces the sitemap

`/robots.txt` SHALL carry an absolute `Sitemap:` line. It is the one URL every
crawler fetches unprompted, so it is where the sitemap has to be declared.

#### Scenario: the sitemap is discoverable without being submitted
- **WHEN** `/robots.txt` is fetched
- **THEN** it names the absolute sitemap URL
- *Verifies:* `test_robots_points_at_the_sitemap`

### Requirement: lastmod only where a date exists

Sitemap entries SHALL carry `<lastmod>` only when the underlying record has a
real date (a water's `added_at`). Static pages SHALL carry none rather than
today's — a `lastmod` that changes on every fetch is one a crawler learns to
ignore.

#### Scenario: dated fichas, undated static pages
- **WHEN** one catalogue water declares `added_at`
- **THEN** exactly one `<lastmod>` appears, holding that date
- *Verifies:* `test_sitemap_dates_only_what_it_knows`

### Requirement: Structured data claims only what the catalogue holds

Pages SHALL emit JSON-LD describing themselves: a water as `Product` (brand,
category, declared minerals as `PropertyValue`, `mg/L` except pH) plus a
`BreadcrumbList`; a region listing as `ItemList` in the order shown; the home
page as `WebSite`.

It SHALL NOT emit `offers`, `aggregateRating`, `review` or any price — the
catalogue holds none of them, and claiming them to chase a rich result is how
a site earns a manual action. The home page SHALL NOT declare a
`SearchAction`: the catalogue filter is client-side, so there is no search URL
to give a crawler.

Breadcrumbs SHALL route through the water's province page, which serves real
content to an anonymous visitor (see `water-similarity`), and SHALL skip that
step — renumbering, leaving no gap — when the province is unknown.

#### Scenario: only declared minerals, correctly united
- **WHEN** a water declares dry residue, sodium and pH
- **THEN** exactly those three appear, `mg/L` on the minerals and no unit on pH
- *Verifies:* `test_a_water_publishes_its_declared_minerals_and_nothing_else`,
  `test_ph_carries_no_unit_but_minerals_do`

#### Scenario: nothing invented
- **WHEN** any ficha's structured data is serialised
- **THEN** it contains no offers, rating, review or currency
- *Verifies:* `test_no_price_rating_or_availability_is_ever_claimed`,
  `test_the_site_claims_no_search_action`

#### Scenario: the trail reaches the region page
- **WHEN** a water declares a province
- **THEN** the breadcrumb runs Catálogo → province → water, positions 1-3
- **AND** a water with no province runs Catálogo → water, positions 1-2
- *Verifies:* `test_breadcrumbs_route_through_the_province_page`,
  `test_a_water_without_a_province_skips_that_crumb`

#### Scenario: the markup a browser receives actually parses
- **WHEN** a ficha is served
- **THEN** its `<script type="application/ld+json">` is parseable JSON holding
  a `Product` and a `BreadcrumbList`
- *Verifies:* `test_a_ficha_serves_valid_json_ld`

### Requirement: A shared link previews real content

Pages SHALL pass an `og:image` when the content they show has a photo — the
water's own on a ficha, the first available bottle on a listing — and SHALL
declare `summary_large_image` only then, falling back to `summary` otherwise.
Every page SHALL declare `og:site_name` and `og:locale`.

#### Scenario: a region link previews a bottle from that region
- **WHEN** a place listing whose first water has a photo is shared
- **THEN** that photo is the `og:image` and the card is `summary_large_image`
- *Verifies:* `test_a_shared_place_link_previews_a_real_bottle`,
  `test_a_photoless_water_declares_no_image`
