# biwenger_api

Cloud Run **Service** (`biwenger-api`) that exposes the Biwenger business
logic over HTTP. Called by:

* the Telegram bot, once per command (low-latency synchronous HTTP);
* Cloud Scheduler, once per day (the digest cron).

Deployed with `--no-allow-unauthenticated`. Invokers authenticate with an
OIDC ID token; the bot's and the Scheduler's service accounts both have
`roles/run.invoker` on this service.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET`  | `/health` | Liveness. **Do not use `/healthz`** — Google Frontend reserves it on `*.run.app`. |
| `GET`  | `/version` | `{service, commit, deploy_time}` |
| `GET`  | `/teams` | All managers + market (was `/analizar`) |
| `GET`  | `/teams/mine` | My squad (was `/myteam`) |
| `GET`  | `/market` | Transfer market (was `/mercado`) |
| `POST` | `/lineups/auto-pick` | Pick + apply lineup (was `/alinear`) |
| `GET`  | `/budget/recommendations[?top=N]` | Top-N affordable clausulazo targets per position |
| `POST` | `/digests/daily` | Cron only — my team + market |

Convention: `GET` when the endpoint only **reads** from Biwenger / JP (sends
PNG to Telegram as a side effect of the response). `POST` when it mutates
external state (Biwenger lineup PUT, scheduled cron tick).

## Local dev

```bash
bazel run //packages/biwenger_tools/api:api_local
```

```bash
curl localhost:8080/health
curl localhost:8080/version
```

## Tests

```bash
bazel test //packages/biwenger_tools/api:api_tests --test_output=streamed --test_arg=-v
```

## Deploy

CI on push to `master` when `packages/biwenger_tools/api/**`, `core/**`,
`tools/**`, `docker/**` or `MODULE.bazel` changes. Cloud Run resource name:
`biwenger-api`.

## Code layout

```
api/
├── app.py                # Flask routes (thin shells)
├── config.py             # Secrets + URLs + JP token
├── player_formatting.py  # Status/position helpers (status_emoji, short_position)
├── logic/
│   ├── actions.py        # run_all_teams, run_my_team, run_market, run_auto_pick_lineup
│   ├── digests.py        # run_daily — the cron
│   ├── recommendations.py# run_recommendations — /budget/recommendations
│   ├── lineup.py         # pick_lineup + format_lineup_message (backtracking + memoised)
│   ├── image_formatter.py# matplotlib PNG renderer
│   ├── player_matching.py# Biwenger ↔ JP name matching
│   └── rows.py           # build_squad_rows, build_market_rows
└── tests/
```

Every handler reuses the same `_prepare_context()` helper (JP health check,
JP index, Biwenger session) so each endpoint stays small. The PNG renderer
and the JSON recommendations endpoint share `build_squad_rows` — the row
dict carries both formatted strings (`Clausulable`, `Cláusula`) and raw
ints (`clause_value`, `clausulable_now`).
