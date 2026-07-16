# Jornada Perfecta — private API

Unofficial API consumed by `core/sdk/jp.py` for Automanager (SofaScore) player
ratings. Discovered by intercepting the Android app — see
`docs/technical/reverse-engineering/frida-android-intercept.md` for the method
and `scripts/extract_token.sh` there for token recovery.

## Endpoint

```
GET https://www.jornadaperfecta.com/api/fitness-daily
```

| Param | Value | Meaning |
|---|---|---|
| `auth` | (token) | Hardcoded in the app's JS bundle. We store it as `jp_auth_token` inside the `biwenger-credentials-regional` secret — never in git. |
| `competition` | `1` | LaLiga |
| `score` | `2` | SofaScore (the Automanager system) |
| `limit` | `600` | Full league in one page |
| `showPredict` | `true` | Include predictions |

Headers: `user-agent: AppBlog/Android`, `accept: application/json, text/plain, */*`.

## Response shape

Each player carries a `predict` list; the entry with `type == 2` is the
Automanager score: **`predict[type=2].rate` is exactly the number the app
shows** (e.g. Vini Jr = 910). This is the `SF` used across the api endpoints
(auto-bid tiers, lineup picker, digests).

Every `predict` also carries `updated_at` (Unix timestamp) marking when JP
recalculated it. JP refreshes the whole league as a batch per `score_type`,
writing over a few minutes — so timestamps within a batch differ slightly
across players, and the batch matches the "Última actualización" shown in
the app.

## Caching (`core/sdk/jp.py`)

`fetch_all_players` caches in-process per `(competition, score_type)`. Before
serving the cache it fires a cheap `limit=5` probe (~200 ms) and compares
`max(updated_at)` against the cached value — equal means fresh, different or
failed probe means full refetch. Cold cache skips the probe. Probing several
players instead of one matters: a single player's `updated_at` can be a no-op
inside an otherwise-new batch.
