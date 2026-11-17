# Web interfaces and Modern Web Guidance

Every web interface the owner runs is held to Google Chrome's
[Modern Web Guidance](https://github.com/GoogleChrome/modern-web-guidance):
accessibility, CSS, forms, performance, security, privacy and visual design,
with Baseline browser-support rules for each recommendation.

- **Where it lives:** vendored as a skill in
  [`system/skills/modern-web-guidance/`](../../system/skills/modern-web-guidance/)
  (Apache 2.0, upstream commit in its `UPSTREAM` file). `scripts/install-system.sh`
  installs it into `~/.claude/skills/`, so every repo on the Mac has it.
- **How it is used:** the `web` rule (`system/rules/web.md`). Read the guides from disk; do
  not run the skill's `npx` commands.
- **Updating it:** `bash scripts/sync-web-guidance.sh`, review the diff, PR,
  then `scripts/install-system.sh`.

## Review of 2026-11

Six sites were checked against one checklist built from the guidance: document
basics, names/roles/keyboard, contrast, forms, overlays and tables,
performance, responsive type, dark mode, motion, security, third parties, SEO
and consistency. The method:

- Source read in full or by pattern search.
- Live pages loaded in headless Chromium at 320/390/1440 px, in dark mode and
  with reduced motion.
- Lighthouse run locally, never through an external analyser.
- household from tracked source only, and wishlist `/admin` from source only.

Lighthouse, mobile (performance / accessibility / best practices / SEO):

| Page | Scores | LCP |
|---|---|---|
| jorgelillo7.github.io `/` | 99 / 97 / 100 / 100 | 0.9 s |
| Biwenger `/26-27/` | 92 / 95 / 100 / 82 | 2.7 s |
| Biwenger `/reglamento` | 86 / 94 / 96 / 82 | 3.0 s |
| be_water `/` | 85 / 93 / 100 / 100 | 3.6 s |
| chucknorris_bot `/` | 99 / 84 / 100 / 90 | 1.6 s |
| wishlist `/` | 90 / 94 / 100 / 58 (noindex by design) | 3.5 s |

### What to fix first, across sites

Done since the review: Biwenger's escaping, contrast (`text-gray-500`, white text on `#2f855a`) and keyboard (focus ring, `aria-expanded`, the Tabla de Justicia rows and cards as buttons) in #772; wishlist in #771; chucknorris_bot (headers, CSP, title on phones, landmarks, share metadata, red text contrast, focus ring) in #763; jorgelillo7.github.io in that repo's PR #19. The items below still name them for the record.

Ordered by impact per unit of work. S = small, M = medium, L = large.

1. **Biwenger: escape `innerHTML`** (S).
   - `templates/salseo.html:150-158` and `templates/mercado.html:159-263`
     interpolate league members' titles and team names unescaped.
   - The nonce CSP stops scripts, so this is markup injection. It was not
     tested with a payload.
   - Reuse `escapeHtml` from `index.html:108-114`, moved to `base.html`.
2. **Security headers** (S each).
   - **chucknorris_bot sends none:** `bot/app.py:21` never calls
     `add_security_headers`.
   - **household Worker:** lacks `frame-ancestors`, `X-Frame-Options` and
     `nosniff` (`deploy/worker.js:6-10`).
3. **chucknorris_bot title is clipped on every phone** (S):
   `clamp(4.5rem, 14vw, 10rem)` in `templates/index.html:75`; lower the floor.
4. **Text compression in the Flask apps through `core/web`** (S).
   - Biwenger `/26-27/salseo` serves 221 KiB of uncompressed HTML.
   - be_water's home serves 86 KiB.
5. **Stop lazy-loading the LCP image** (S each); add `fetchpriority="high"`.
   - be_water: `_water_card.html:17-20`.
   - wishlist: `list.js:150`.
6. **Contrast pass**, then record the new values in each `DESIGN.md` (S per site).

   | Site | Fails today |
   |---|---|
   | Biwenger | `text-gray-400` 2.4:1 (80 uses); white on the green accent 3.25:1 |
   | be_water | white on `sky-500` 2.77:1; `text-slate-400` 2.45:1 |
   | wishlist | `--muted` 3.5:1 in the light theme |
   | chucknorris_bot | red label text 4.0:1 |

7. **Biwenger keyboard** (M).
   - The hamburger's focus is invisible.
   - No `aria-expanded` or `aria-pressed` anywhere.
   - Clickable `<tr>`, `<div>` and `<img>` should be `<button>`s.
8. **Tailwind build step** for Biwenger and be_water (M, once). Already in
   `PENDING.md`. It is the precondition for:
   - dropping `'unsafe-inline'` and the CDN host from the CSP;
   - dark mode.
9. **YouTube on `/reglamento`** (S): about 880 KiB and third-party cookies,
   loaded eagerly. Use `youtube-nocookie.com` with `loading="lazy"`, or a
   façade.
10. **Labels and accessible names** (S).
    - Biwenger's search and filter inputs use placeholders only.
    - be_water's nickname field has the same problem.
    - be_water's mobile nav has emoji-only names; use `sr-only` instead of
      `hidden`.
11. **Native `<dialog>`** (M) for four hand-built overlays: three in Biwenger,
    one in be_water.
12. **Sharing metadata** (S).
    - chucknorris_bot has no description and no Open Graph.
    - be_water's meta description shows a literal "?" when a water has no
      data (`routes/main.py:99-105`).
    - Biwenger is indexable: decide on `noindex`.
13. **Self-host fonts** (S each): wishlist, chucknorris_bot, then the two
    Tailwind apps.
14. **Shared headers in `core/web/headers.py`** (S): `Permissions-Policy`,
    COOP, and a `__Host-` cookie name.
15. **`color-scheme` declarations everywhere** (S), then `px` → `rem` in
    wishlist and household (S). Dark themes for Biwenger and be_water come
    after item 8 (L).

### Per site, beyond the list

- **jorgelillo7.github.io:** fixed in that repo's README and content round,
  together with the content review.
- **Biwenger web:** fixed in #772 and #773: escaping, contrast,
  keyboard, a hidden `<h1>` per page from its title, `scope` on every column
  header, labels on every search and filter input, the three overlays as
  `<dialog closedby="any">`, the zoomable images as buttons, the YouTube
  façade on `youtube-nocookie.com`, `noindex`, and the Tabla de Justicia
  header wrapping at 320 px. Static files are served immutable under a
  content-versioned URL (`core/web/static.py`, be_water too). Open: dark mode
  waits on the Tailwind build (item 8).
- **be_water:** fixed in #774: the first card photos eager with
  `fetchpriority`, `text-slate-500` and white text on `sky-700`, mobile nav
  names kept for screen readers, "Entrar" fitting at 320 px, no "?" in the
  meta description, the photo viewer as a `<dialog>` with the bottle as a
  button, `motion-safe:animate-bounce`, card titles as `<h2>` on the
  catalogue, and `aria-pressed` on the filters. Open: the Tailwind build
  (item 8).
- **chucknorris_bot:** no `<main>` or real headings; `100vh`; a global reset.
- **wishlist:** closest to the guidance. Fixed: the first photos load eagerly and
  the first with `fetchpriority="high"`; `--muted` is 4.9:1 on the page; the grid is
  no longer a live region (a hidden status line reads the count); the admin photo
  buttons are `<button>`s; font sizes in `rem`; Fraunces self-hosted, with the CSP
  down to `'self'`; seed photos and the font cached immutable; `HEAD` on uploaded
  photos. Open: photos have no `srcset`.
- **household:**
  - `script-src 'unsafe-inline'` where a hash would do;
  - font sizes are in `px`;
  - the passphrase field has no visible label;
  - table headers have no `scope`.
- **interactive_fiction** (reader and 3D draft), reviewed separately after
  its November work. Fixed: restart's armed name, translucent backgrounds in
  the contrast check, focus after a setting redraws the page, focus on the
  heading after a route change, the copy-link status, `og:image:alt` and
  `og:image:type`, `color-scheme`, the root `<title>`, `/assets/*` immutable
  and checked live, a 1280 px width, the first index covers eager, reduced
  motion keeping colour and opacity, the code field's border, `<main>` in a
  scene page, the 3D draft's `<progress>`, indeterminate bar and headers,
  the settings and status sheets as native `<dialog>`s (`dialog.md`), and
  the title picture as a discoverable `<img>` preloaded by the build.
  `font-size-adjust: from-font` was tried and measured in Chrome, with the
  fonts loaded and with them blocked: it moved nothing, since it takes the
  ratio from the face in use, the fallback itself during a swap. It was
  removed. Open items:
  - control borders under 3:1: `tw-link` 2.32, `.button.secondary` 2.57,
    `.credit-links a` 2.15;
  - `:focus-visible` sets `border-radius`, which reshapes elements;
  - a speaker is told apart by colour alone (the author's call);
  - 3D draft: the idle camera sway ignores the effects setting, `px` font
    sizes and `text-align: left`, the sound icon has no background, a drag
    does not clear on `lostpointercapture`, no arrow keys to look around,
    and `script-src` waits for a test of the renderer on Cloudflare.
