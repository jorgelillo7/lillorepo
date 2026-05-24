# Biwenger Tools

## Does your Biwenger league drama deserve to live forever?

Do you enjoy the banter and trash talk between friends that keeps your leagues alive? Does it annoy you when it all gets buried under ads or wiped when the season resets?

Here is the solution! This project is a **backup + web + analysis** system so your most epic messages, legendary feuds, and tactical breakdowns are preserved and accessible. And yes, it was built with more than a little help from AI ;)

---

## Packages

Four packages working together to archive, visualise and analyse data from a Biwenger league. Each one has its own README with entry point, gotchas, and local dev notes — this file is just the index.

| Package | Deployment | Detail |
|---|---|---|
| [`scraper_job/`](scraper_job/README.md) | Cloud Run Job (weekly cron) | Scrapes the league board and writes to Firestore (deterministic doc IDs, idempotent) |
| [`web/`](web/README.md) | Cloud Run Service | Flask dashboard at https://biwenger-summary-pjpqofuevq-no.a.run.app/ — reads Firestore (server-side queries + composite index) plus Sheets for `ligas_especiales` / `trofeos` |
| [`api/`](api/README.md) | Cloud Run Service | Biwenger business logic over HTTP — `/teams`, `/lineups/auto-pick`, `/budget/recommendations`, `/market/auto-bid`, `/digests/daily`, etc. Renders PNG + posts to Telegram |
| [`bot/`](bot/README.md) | Cloud Run Service | Telegram webhook → calls `api` with an OIDC ID token |

## How they fit together

```
┌────────────┐  weekly cron     ┌──────────────┐
│ scraper_job│ ────────────────▶│   Firestore  │
└────────────┘                  │  (native, EU)│
                                └──────┬───────┘
                                       │ server-side query (composite index)
                                       ▼
                               ┌───────────────┐
   browse ─────────────────────│      web      │
                               │ Cloud Run Svc │
                               └───────────────┘

                          ┌──────────────────────────────┐
                          │   api  (Cloud Run Service)   │
                          │   Flask + matplotlib         │
                          │   /teams /market /lineups    │
                          │   /budget /market/auto-bid   │
                          │   /digests/daily             │
                          └──────────────────────────────┘
                              ▲                    │
                              │ ID token           │ sendPhoto / sendMessage
                              │ (run.invoker)      ▼
                          ┌───────────┐       ┌────────────┐
   Telegram ──webhook────▶│   bot     │       │  Telegram  │
                          │ (Service) │       │            │
                          └───────────┘       └────────────┘
                              ▲
                              │ HTTPS + OIDC
                          ┌──────────────────┐
                          │ Cloud Scheduler  │ 09:00 Madrid — digest + auto-bid
                          └──────────────────┘
```

## Operational commands

See [`docs/operations.md`](../../docs/operations.md) for the full reference (build, test, local run, deploy per package).

## Stack at a glance

Python 3.13 · Flask · matplotlib · BeautifulSoup · `requests` · Bazel (`@pypi`) · Cloud Run + Cloud Run Jobs + Cloud Scheduler · Secret Manager · Artifact Registry · Firestore · Google Sheets API.
