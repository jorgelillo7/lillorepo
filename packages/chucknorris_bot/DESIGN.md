---
name: ChuckBot
description: Chuck Norris Telegram bot landing page — bold, tactical, no-nonsense
colors:
  background: "#0d0d0d"
  surface: "#1a1a1a"
  border: "#2a2a2a"
  text: "#f5f5f5"
  muted: "#888888"
  accent: "#dc2626"
  accent-hover: "#b91c1c"
  gold: "#f59e0b"
typography:
  heading:
    fontFamily: Black Ops One
    fontWeight: "400"
    letterSpacing: -0.02em
    usage: Hero H1 and origin card heading only
  body:
    fontFamily: Inter
    fontWeight: "400"
    fontSize: 1rem
    lineHeight: 1.6
  code:
    fontFamily: Courier New, monospace
    color: "{colors.gold}"
    usage: Command names (/random, /science, etc.)
rounded:
  sm: 4px
  md: 8px
  pill: 999px
components:
  hero-badge:
    background: "rgba(220,38,38,.12)"
    borderColor: "rgba(220,38,38,.3)"
    textColor: "{colors.accent}"
    borderRadius: "{rounded.pill}"
  cta-button:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    hoverBackgroundColor: "{colors.accent-hover}"
    borderRadius: "{rounded.md}"
    fontWeight: "700"
  cmd-card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    hoverBorderColor: "{colors.accent}"
    hoverTranslateY: -3px
    borderRadius: "{rounded.md}"
  origin-card:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    borderRadius: "{rounded.md}"
  year-badge:
    background: "rgba(245,158,11,.12)"
    borderColor: "rgba(245,158,11,.3)"
    textColor: "{colors.gold}"
    borderRadius: "{rounded.sm}"
---

## Overview

Single-page landing for a Telegram bot that serves Chuck Norris facts. The design leans hard into the Chuck Norris brand: brutal, dark, no-nonsense. Near-black background, tactical red accent, amber-gold for vintage touches. One CTA. No images. No frameworks.

Not a product page — more like a dojo entrance. Come for the button, leave with a fact about roundhouse kicks.

## Colors

Aggressive and intentional. Red on near-black is maximum contrast; gold is the warmth that stops it from feeling hostile.

- **Background (#0d0d0d):** Near-black. Sets the tone immediately — this isn't a corporate SaaS landing.
- **Surface (#1a1a1a):** Slightly lighter — cards and panels lift off the background without going grey.
- **Border (#2a2a2a):** Barely-visible structural separation. Not decorative.
- **Text (#f5f5f5):** Off-white. Easier on the eyes than pure white on a dark background.
- **Muted (#888888):** Secondary text — taglines, command descriptions, footer, origin body copy.
- **Accent (#dc2626):** Chuck Norris red. The only warm color in the UI. Hero glow, CTA button, section labels, card hover borders. One active element per visual zone — don't stack multiple red things.
- **Gold (#f59e0b):** Reserved for two things: monospace command names and the "2015 → 2026" year badge. Adds warmth without competing with red.

## Typography

Two fonts. Strict roles.

- **Black Ops One** — military stencil cut. Used only for the `CHUCKBOT` hero title and the origin card heading. Never body copy. The CSS `clamp(4.5rem, 14vw, 10rem)` scales the hero from 375px mobile to 1400px desktop without a media query.
- **Inter** — clean, modern, legible at any density. Everything else: tagline, descriptions, footer, origin text, section labels.
- **Courier New** (fallback monospace) — command names only, in `--gold`. Makes it immediately obvious these are bot commands, not prose.

## Layout

Single centered column, `max-width: 800px`. Sections separated by 1px `--border` dividers. No cards between sections — just padding and labels.

Hero is full-bleed with a CSS-only radial gradient glow behind the title (`::before` pseudo-element, `rgba(220,38,38,.18)`). No images, no SVG backgrounds.

The commands grid uses `auto-fill` with a `150px` minimum — 5 cards land in one row on desktop, wrap naturally on mobile.

## Components

### Hero Badge
Pill chip above the H1. Semi-transparent red background + border. Labels the context ("Telegram Bot"). Used once, in the hero only.

### CTA Button
The primary action. Red fill, white text, Telegram SVG icon inline. Hover darkens to `--accent-hover` and lifts 2px. The only filled button on the page.

### Command Card
5-card responsive grid. Each card: emoji → monospace command in gold → short description in muted. Hover lifts 3px and switches border to `--accent`. No click action — these are informational.

### Origin Card
Dark surface card. Contains: gold year-badge → Black Ops One heading → two paragraphs in muted. The one section where the tone softens. `em` text inside uses `--text` (near-white) to make quoted strings pop.

## Do's and Don'ts

- **Do:** Keep Black Ops One to H1 and the origin heading. Nowhere else.
- **Do:** Use `clamp()` on the hero — don't hardcode a pixel size for H1.
- **Do:** One red focal point per section. The glow, the CTA, the section labels, and the card hover share the accent — they don't compete because they're in different zones.
- **Don't:** Add images. The page is intentionally CSS and text only.
- **Don't:** Lighten the background. The contrast of `--text` on `#0d0d0d` is load-bearing.
- **Don't:** Use Black Ops One below 1rem or in a paragraph context.
- **Don't:** Add a second CTA or a nav bar. One exit: the Telegram button.
