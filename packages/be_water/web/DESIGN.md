---
name: Be Water
description: Open catalog of Spanish mineral waters — light, fresh, product-grade
colors:
  primary: "#0f172a"
  secondary: "#64748b"
  muted: "#64748b"
  background: "#f8fafc"
  surface: "#ffffff"
  border: "#e2e8f0"
  accent: "#0ea5e9"
  accent-hover: "#0284c7"
  accent-fill: "#0369a1"
  accent-gradient-to: "#22d3ee"
  favorite: "#e11d48"
tones-by-mineralization:
  muy-debil: sky
  debil: teal
  fuerte: amber
  muy-fuerte: rose
  desconocida: slate
typography:
  heading:
    fontFamily: Inter
    fontWeight: "800"
    fontSize: 3rem
    letterSpacing: -0.025em
  body:
    fontFamily: Inter
    fontWeight: "400"
    fontSize: 0.875rem
    lineHeight: 1.6
  label:
    fontFamily: Inter
    fontWeight: "600"
    fontSize: 0.75rem
rounded:
  pill: 9999px
  xl: 12px
  "2xl": 16px
  "3xl": 24px
spacing:
  card-padding: "16px (p-4)"
  panel-padding: "24-32px (p-6 sm:p-8)"
components:
  water-card:
    surface: "{colors.surface}"
    ring: "ring-1 ring-slate-200"
    hover: "hover:ring-sky-300 hover:shadow-lg hover:-translate-y-0.5"
    radius: "{rounded.2xl}"
    header: "h-24 gradient from-{tone}-50 to-{tone}-100"
  chip:
    active: "bg-slate-900 text-white"
    inactive: "bg-white ring-1 ring-slate-200 text-slate-600"
    radius: "{rounded.pill}"
  button-primary:
    backgroundColor: "{colors.accent}"
    hoverBackgroundColor: "{colors.accent-hover}"
    textColor: "#ffffff"
    radius: "{rounded.pill} (nav) / {rounded.2xl} (forms)"
  input:
    focusRing: "focus:ring-2 focus:ring-sky-400"
    radius: "{rounded.xl} — {rounded.2xl} for hero search"
  mineral-bar:
    track: "bg-slate-100 h-2 rounded-full"
    fill: "bg-gradient-to-r from-sky-400 to-cyan-400"
    scale: "linear, capped at 400 mg/L"
---

## Overview

Product-grade landing feel for a tiny collaborative catalog: airy, rounded,
one strong accent. Where Lloros League is a dense private intranet, Be Water
is **outward-facing** — it may end up on LinkedIn/Twitter, so every screen
must look shareable: generous whitespace, big friendly numbers, no clutter.

The identity is the water itself: 💧 for still, 🫧 for sparkling, and a
**tone system keyed to the EU mineralization class** so the color always
carries meaning (never decoration).

## Colors

Neutral slate base + one live accent (`sky-500`), same discipline as the
other webs — the accent marks interactive elements only. White on `sky-500` is
2.8:1, so a filled button with white text uses `sky-700` (5.9:1, hover
`sky-800`). The lightest grey for text is `slate-500` (4.6:1 on the page);
`slate-400` (2.5:1) is never text.

The **mineralization tone system** is the signature rule:

- `muy débil` → **sky** (light, airy — Bezoya territory)
- `débil` → **teal** (the everyday-water middle ground — Solán, Lanjarón)
- `fuerte` → **amber** (heads-up: mineral-heavy)
- `muy fuerte` → **rose** (Vichy Catalán energy)
- unknown → **slate**

Tones color the card header gradient (`from-{tone}-50 to-{tone}-100`), the
TDS figure (`text-{tone}-700`) and the class badge. A water's tone must be
consistent across every surface it appears on. ❤️ favorite uses rose and is
exempt from the accent-discipline rule.

Tailwind build note: the CSS is compiled at build time (`tailwind.config.js`,
`//packages/be_water/web:tailwind`), and the scanner only sees class names
written out in full. Tone classes are composed in Jinja (`from-{{ tone }}-50`),
so the config safelists every shape the templates use for every tone. A new
tone, or a new `…-{{ tone }}-…` shape, goes in `TONES` or `TONE_SHAPES` there,
or it renders unstyled.

### Dark mode

The site follows the system setting (`prefers-color-scheme`) until the reader
pins the other scheme with the sun/moon button in the nav; it works as in
Biwenger (`packages/biwenger_tools/web/DESIGN.md` § Dark mode). Every palette colour the templates use reads a CSS variable
(`tools/bazel/tailwind_dark_palette.js`, configured in `tailwind.config.js`):
tinted backgrounds go deep and text goes light, slate has a hand-tuned ramp
(page `slate-50` → #020617, cards `white` → #0f172a), and tone gradients become
dark tints of the same hue. Write plain classes, no `dark:` variants. A colour
that must not flip — the photo viewer over its dark backdrop — is written as
an arbitrary value (`text-[#fff]`). The nav glass (`--glass`) and
`--accent` are tokens in `tailwind.config.js`; photos are dimmed slightly
(`brightness(.9)`, a `darkRules` entry). Never write a `prefers-color-scheme`
media query in a template: it would ignore the button.

## Typography

**Inter only**, weights 400/500/600/800. Hierarchy comes from weight and
size, not from mixing families:

- Hero/headings: 800, tight tracking (`tracking-tight`).
- The gradient headline (`text-transparent bg-clip-text from-sky-500
  to-cyan-400`) is reserved for the home hero — one per site.
- Numbers (TDS, mineral values): 700-800 + `tabular-nums`.
- Micro-labels (units, badges): 600, uppercase, `text-[10px]-[11px]`,
  wide tracking.

## Layout

- **Max-width:** `max-w-6xl` (catalog grid breathes on desktop); forms and
  empty states constrain to `max-w-md/xl`.
- **Grid:** 1 column mobile → 2 `sm` → 3 `lg`. Mobile-first always.
- **Nav:** sticky glass bar (`backdrop-filter: blur(12px)` + `rgba(255,255,255,.82)`),
  56px tall, with inline nickname login. Nav labels collapse to emoji-only
  on mobile but stay as the link's name (`sr-only sm:not-sr-only`, the emoji
  `aria-hidden`); under 360 px the "Be Water" wordmark does the same so
  "Entrar" fits.
- Footer is whisper-quiet: `text-xs text-slate-500`, commit hash included.

## Components

### Water card (`_water_card.html`)

The atomic unit, shared by catalog / similars / recommendations — change it
once, it changes everywhere. Anatomy: tone-gradient header (emoji + big TDS
figure right-aligned) → body (name, 📍 province · community, class badge).
Whole card is one `<a>`; hover lifts it (`-translate-y-0.5` + `shadow-lg` +
`ring-sky-300`). Carries `data-name` / `data-min` for client-side filtering.

### Filter chips

Pill buttons; active chip inverts to `bg-slate-900 text-white` (not accent —
the accent stays for actions). One active chip at a time.

### Mineral bars

Composition rows render a 2px-tall track with a sky→cyan gradient fill,
linear scale capped at 400 mg/L (everything above saturates — the exact
number is printed beside the bar anyway). pH renders as number only.

### Empty states

Always: big emoji + one short sentence + a link that moves the user forward
(seed the catalog, go mark favorites, add the first water of a region).
Never a bare "no results".

## JS Conventions

Vanilla JS, same doctrine as `biwenger_tools/web/DESIGN.md` (originalHtml
restore, no frameworks). This app additionally prefers **filtering
server-rendered DOM** (`classList.toggle('hidden')` on cards) over
re-rendering — Jinja renders once, JS only shows/hides.

## Do's and Don'ts

- **Do:** keep every screen shareable — if a screenshot would look bad on
  a timeline, it's not done.
- **Do:** derive color from mineralization; it's the product's vocabulary.
- **Don't:** introduce a second font family or a second live accent.
- **Don't:** exceed `shadow-lg` or stack more than one gradient per card.
- **Don't:** add a tone without updating this file and checking the CDN
  caveat above.
