---
name: Lloros League
description: Fantasy football league dashboard — casual but opinionated
colors:
  primary: "#2d3748"
  secondary: "#4a5568"
  muted: "#718096"
  background: "#f7fafc"
  surface: "#ffffff"
  border: "#e2e8f0"
  accent: "#38a169"
  accent-hover: "#276749"
  accent-light: "#c6f6d5"
  danger: "#e53e3e"
  warning: "#d69e2e"
  calendar-liga: "#38a169"
  calendar-copa: "#d69e2e"
  calendar-h2h: "#3182ce"
  calendar-mercado: "#e53e3e"
  calendar-draft: "#805ad5"
  calendar-otros: "#718096"
typography:
  heading:
    fontFamily: Oswald
    fontWeight: "700"
    fontSize: 3rem
    letterSpacing: 0.05em
  subheading:
    fontFamily: Oswald
    fontWeight: "500"
    fontSize: 1.5rem
  body:
    fontFamily: Roboto
    fontWeight: "400"
    fontSize: 1rem
    lineHeight: 1.6
  label:
    fontFamily: Roboto
    fontWeight: "500"
    fontSize: 0.875rem
rounded:
  sm: 4px
  md: 8px
  lg: 12px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 32px
  xl: 48px
components:
  card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    borderRadius: "{rounded.lg}"
    padding: "24px (p-6)"
  nav-link:
    color: "{colors.secondary}"
    activeColor: "{colors.primary}"
    activeBorderColor: "{colors.accent}"
    activeFontWeight: "700"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    hoverBackgroundColor: "{colors.accent-hover}"
    borderRadius: "{rounded.md}"
  pagination-active:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    borderColor: "{colors.accent}"
  search-input:
    focusRingColor: "{colors.accent}"
    borderRadius: "{rounded.lg}"
---

## Overview

Sport dashboard with personality — part football scoreboard, part private league noticeboard. Tone is informal but the layout is clean. The green accent references the pitch; dark greys give readability without feeling corporate.

This is not a commercial product — it's a private league intranet. The design can be dense and direct; there's nothing to sell.

## Colors

`#38a169` is the only "live" colour in the palette and must be used sparingly:

- **Primary (#2d3748):** Main text, content headings, UI icons.
- **Secondary (#4a5568):** Secondary text, labels, metadata.
- **Muted (#718096):** Dates, footnotes, lower-hierarchy content.
- **Accent (#38a169):** Active nav indicator, confirmed-action buttons, active page numbers, author highlights. The only live colour — don't use it as decoration.
- **Background (#f7fafc):** Page base, slightly off-white to reduce eye fatigue vs. pure white.
- **Surface (#ffffff):** Cards and panels elevated above the background.
- **Border (#e2e8f0):** Dividers and card borders — subtle, not prominent.

## Typography

Two families, clearly separated roles:

- **Oswald** for the `LLOROS LEAGUE` logotype and high-impact section headings. Always weight 500 or 700, never lighter. Wide tracking (0.05em) on the main heading reinforces the sport character.
- **Roboto** for all body text: messages, tables, forms, metadata. Readable at high information density.

Never mix both families in the same text block.

## Layout

- **Max-width:** `max-w-4xl` (56rem) centred — enough for data tables without becoming too wide on desktop.
- **Page padding:** `p-4` on mobile, `p-8` on desktop.
- Cards use `shadow-md` at rest and `shadow-lg` on hover for depth without excess.

## Components

### Card

The basic content unit. White background, subtle `#e2e8f0` border, `rounded-xl` radius (12px), `p-6` padding. All content pages use cards as their main container.

### Sticky Nav (UI 2.0)

`base.html` implements a sticky bar (`position: sticky; top: 0; z-index: 20`) with two layers:

- **Mobile bar** (`md:hidden`): logo + hamburger button with two SVGs (menu / close) toggled via `classList.toggle('hidden')`. When open, shows a vertical link panel with season pills below.
- **Desktop nav** (`hidden md:flex`, 48px tall): logo + `.nav-link` items + season pill dropdown. The active link uses `border-bottom: 2px solid #38a169`; inactive links use `border-bottom: 2px solid transparent` to prevent layout shift.

Don't use background colour on the active item — the underline is the indicator. The season selector on desktop is a dropdown with `stopPropagation` and click-outside close.

On **mobile**, the active link uses `bg-green-50 text-green-700` (no underline — the background fill replaces it in the vertical panel context).

### Search Input

Full-width input with `focus:ring-2 focus:ring-green-500`. The focus ring must be clearly visible.

### Pagination

Bordered buttons, `rounded-md` radius. The active page inverts colours: `#38a169` background, white text.

### Calendar category colours (`/calendario` only)

Scoped exception to the "one live colour" rule: the calendar page categorises
events by keyword match on their title (`liga`, `copa`, `h2h`, `mercado`,
`draft`, else `otros`) and colour-codes them as light `bg-{color}-100
text-{color}-800` chips so events are scannable at a glance — `calendar-liga`
(green), `calendar-copa` (amber), `calendar-h2h` (blue), `calendar-mercado`
(red), `calendar-draft` (purple), `calendar-otros` (grey, catch-all). These
colours are **only** used for event chips and the category filter pills on
this one page — do not reuse them as decoration elsewhere in the site.

## JS Template Conventions

Vanilla JS only — no frameworks. Standardised patterns for consistency across templates:

### `originalHtml` — restore server-rendered content

When an interaction (search, tab switch) replaces Jinja2-rendered content, store the original HTML on `DOMContentLoaded` and restore it on clear:

```js
const originalHtml = {};
document.addEventListener('DOMContentLoaded', () => {
    originalHtml.tab = document.getElementById('container').innerHTML;
});
function clearSearch() {
    container.innerHTML = originalHtml.tab || '';
}
```

Never reconstruct in JS what Jinja2 already rendered correctly.

### Expandable table rows

Add `data-row-idx` to each `<tr>` and use `insertAdjacentElement('afterend', detailTr)` to insert the detail row. Close any previously open detail before opening a new one (avoids multiple open rows at once).

```js
function toggleRowDetail(idx) {
    document.querySelectorAll('[data-detail-row]').forEach(r => r.remove());
    const anchor = document.querySelector(`[data-row-idx="${idx}"]`);
    if (anchor) anchor.insertAdjacentElement('afterend', buildDetailTr());
}
```

On mobile use a `<div id="card-detail-{i}">` toggled with `classList.toggle('hidden')` instead of inserting rows.

### `AbortController` for fetch with timeout

```js
const controller = new AbortController();
const tid = setTimeout(() => controller.abort(), 5000);
const res = await fetch(url, { signal: controller.signal });
clearTimeout(tid);
```

### Passing server data to JS

Use `{{ data | tojson }}` in a `<script>` block at the top of the JS section. Never hardcode data in JS or make an extra fetch if Jinja2 already has the data available.

```html
<script>
const DATA = {{ rows | tojson }};
</script>
```

### Accordion

Button with `data-target="section-id"` + collapsible div. First item open by default; the rest start with class `hidden`. The chevron uses `classList.toggle('rotate-180', isOpen)`.

## Do's and Don'ts

- **Do:** Use `accent` for a single active interactive element per context.
- **Do:** Keep information density high — this app needs it.
- **Don't:** Use Oswald at weight < 500.
- **Don't:** Add new colours without updating this file first.
- **Don't:** Use shadows heavier than `shadow-lg` — the design is flat with functional shadow.
