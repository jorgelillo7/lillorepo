# Captures

Raw API-discovery exports kept beside the investigation that produced them.

A capture is evidence, not documentation. The notes that read it live in the
doc that links here; this directory holds the original so a later session can
re-read it, diff a second capture against it, or check a claim the notes make.

Root-level captures are gitignored (`openapidevtools.json`, `oraculo.json`) —
that is where the browser extension drops them, and an unreviewed dump must
not be committed from there by accident. Moving one here is the deliberate act
of keeping it.

**Check before adding one.** These are exports of a live browser session. Cookie
and header *names* are fine; a cookie *value*, bearer token or session id is
not, and this repository is public.

| File | Investigation | Taken |
|---|---|---|
| `oraculo-analiticafantasy.json` | [A second projection source](../second-projection-source.md) | Before 2026-09-14 |

## `oraculo-analiticafantasy.json`

An [OpenAPI DevTools](https://github.com/AndrewWalsh/openapi-devtools) export:
`leafMap` of host → path → inferred request/response schema.

25 hosts, of which 22 are ad-tech noise picked up while browsing. The one that
matters is `server.analiticafantasy.com` — Oráculo is a tool inside that site,
so this is the host the whole investigation is about. Checked before committing: 2211
distinct string values, none of them a credential — paths, type names, header
names and numeric enums only.

What it does and does not establish is in the linked doc. Short version: it
found the host, not the projections.
