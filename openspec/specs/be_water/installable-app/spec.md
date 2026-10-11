# Capability: installable-app

Be Water as an app on Android and iPhone home screens: the manifest, the icons
and a service worker whose only job is an offline page.

- **Source:** `packages/be_water/web/routes/main.py` (`manifest`,
  `service_worker`), `static/sw.js`, `static/offline.html`,
  `templates/base.html`; icons from `scripts/generate_web_icons.py be-water-web`
- **Verified by:** `packages/be_water/web/tests/test_routes.py`

---

### Requirement: The site installs as an app

Every page SHALL link a web app manifest (name, standalone display, start URL
and scope `/`, 192 px, 512 px and maskable icons that are all served) and an
apple-touch-icon, and register a service worker served from the root, never
cached. The worker SHALL only add an offline page for navigations; it SHALL NOT
cache anything else, so a deploy is visible on the next load.

#### Scenario: manifest, worker and offline page
- **WHEN** `/manifest.webmanifest` is requested **THEN** it is
  `application/manifest+json` with every install field, and each icon resolves
- **WHEN** `/sw.js` is requested **THEN** it is JavaScript from the root with
  `Cache-Control: no-cache` and a `fetch` handler
- **WHEN** the worker installs **THEN** the offline page it precaches exists and
  runs no script
- **WHEN** any page renders **THEN** it links the manifest and the
  apple-touch-icon and registers the worker
- *Verifies:* `test_the_manifest_declares_an_installable_app`,
  `test_the_service_worker_is_served_from_the_root_and_never_cached`,
  `test_the_offline_page_the_worker_falls_back_to_exists_and_runs_no_script`,
  `test_pages_link_the_manifest_and_register_the_worker`
