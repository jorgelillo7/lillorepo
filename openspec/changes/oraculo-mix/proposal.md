# Mix Oráculo into the projection

## Why

Every lineup, captain, clausulazo and bid this project makes rides on **one
number**: Jornada Perfecta's `SCORE_SF`. The gameweek recorded in
`docs/technical/backend/second-projection-source.md` is what that costs — a
squad JP rated 13-high/0-medium/1-low scored 15 points while a rival rated
8-high/3-medium/6-low scored 93.

A point estimate is an expectation. Analítica Fantasy's Oráculo publishes the
two things JP's single number hides: **whether he starts at all** (a starting
probability) and **a second opinion on the points**.

## What changes

**JP is the base and stays the base.** Oráculo is a second opinion that nudges
it up or down; it never replaces it and never decides alone. If Oráculo is
missing, thin, unreachable or serving the wrong scoring system, every number in
this project is exactly what it is today — and the output says so, because an
unmarked fallback is how a silent regression lives for months.

Every consultation of JP becomes a consultation of JP + Oráculo, across all
seven readers that consume it, and every input stays on the row beside the
output so no export loses a column and the formula stays arguable.

- A `core/sdk/oraculo.py` reader, over two sources.
- A third join on the row, beside Biwenger and JP.
- A `custom_prediction` that blends them, with three levels of fallback to JP.
- The seven readers that consume JP move onto it, one at a time — including
  `offers.py`, which the first draft of this plan missed and which is the one
  that spends money.
- A visible marker whenever the blend did not run.
- Monitoring that twelve months proved silent comes out.

## What does not change

- JP remains the source of truth when Oráculo has no opinion on a player.
- No decision changes until the shadow week says the formula behaves.
- Nothing is read from `/api/`, which `robots.txt` disallows.

## Status

**Feasibility proved, permission decided.** The endpoint was called once and
answers with Biwenger-scored data and the eight lists; the page route covers
the squad the endpoint does not reach. Both `robots.txt` and the terms of
service were read and quoted before the owner decided to proceed on
personal, non-commercial grounds — recorded in `design.md` along with what
that decision obliges: an honestly identified client, one cached call per run,
and a request for express authorisation, which is what would make it durable.
