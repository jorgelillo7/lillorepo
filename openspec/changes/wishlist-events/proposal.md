# Proposal: more than one event on the gift list

The list now lives in D1 and every gift belongs to an event, but the app shows exactly
one: the event marked `current`. This change makes birthdays (and next Christmas) a
first-class thing without a second deployment.

## What is already generic

- Claims, tokens, privacy of names, hiding, deleting and the admin: they know gifts,
  not occasions. A claim is keyed on the gift id, which is unique across events.
- Data: `events`, `recipients (event, id)` and `gifts.event` exist; the admin reads and
  writes the current event only.
- The photo pipeline, the metadata stripping and the upload cap.

## What is Christmas-specific

- Copy in `web/index.html`: the star in the hero and "Elige un regalo…" is neutral
  enough, but the page `<title>`, the manifest names ("Regalos") and the home-screen
  icon (a gift with a star) say nothing about the occasion, which is fine; the hero
  star and any wording about Papá Noel live only in the `subtitle` data. So the copy is
  almost generic already.
- Recipients are two brothers' labels per event; a birthday list needs its own (usually
  one), which `recipients (event, …)` already allows.
- There is no way to create an event, switch `current`, or see another event: today it
  is a `wrangler d1 execute` (OPERATIONS.md).

## Smallest change that makes it multi-event

1. `GET /api/list?event=<slug>` (default: the current event), and `/api/state` limited
   to that event's gifts. The page reads `?evento=<slug>` from its address, the way it
   already reads `?para=` and `?estado=`, so a link opens one list.
2. Access without passwords: an event's slug carries a random part
   (`cumple-lucas-7f3a9c`), the link is the capability, and `current` is the only list
   reachable from `/`. Guests need nothing new; the list of events is never exposed. A
   per-event password would add a login screen and a second cookie for little gain on a
   family list; revisit only if a link leaks.
3. `/admin`: an event picker, "new event" (title, subtitle, recipients) and "make
   current", all admin writes under the existing same-site guard. The add-gift dialog
   writes into the picked event.
4. An `intro` text per event for the line under the title, replacing the fixed
   sentence in `index.html`.

## Not in scope

Per-event admin credentials, deleting a whole event, copying gifts between events.

## Cost

About one migration (`events.intro`), four routes, one admin screen and the tests; no
new service or account step.
