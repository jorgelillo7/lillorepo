#  Biwenger Tools

## 🔥 Does your Biwenger league drama deserve to live forever? 🔥

Do you enjoy the banter and trash talk between friends that keeps your leagues alive? Does it annoy you when it all gets buried under ads or wiped when the season resets?

Here is the solution! This project is a **backup + web + analysis** system so your most epic messages, legendary feuds, and tactical breakdowns are preserved and accessible. And yes, it was built with more than a little help from AI ;)

---

## 📦 Submódulos

Four packages working together to archive, visualise and analyse data from a Biwenger league. Each one has its own README with entry point, gotchas, and local dev notes — this file is just the index.

| Submódulo | Deployment | Detalle |
|---|---|---|
| [`scraper_job/`](scraper_job/README.md) | Cloud Run Job (weekly cron) | Scrapes the league board → CSV → Google Drive |
| [`web/`](web/README.md) | Cloud Run Service | Flask dashboard at https://biwenger-summary-pjpqofuevq-no.a.run.app/ |
| [`api/`](api/README.md) | Cloud Run Service | Biwenger business logic over HTTP — `/teams`, `/lineups/auto-pick`, `/budget/recommendations`, `/digests/daily`, etc. |
| [`bot/`](bot/README.md) | Cloud Run Service | Telegram webhook → calls `api` |

## 🔁 How they fit together

```
┌────────────┐  weekly cron     ┌──────────────┐
│ scraper_job│ ────────────────▶│ Google Drive │
└────────────┘                  │  (CSV files) │
                                └──────┬───────┘
                                       │ read on each request
                                       ▼
                               ┌───────────────┐
   browse ─────────────────────│      web      │
                               │ Cloud Run Svc │
                               └───────────────┘

                          ┌──────────────────────────────┐
                          │   api  (Cloud Run Service)   │
                          │   Flask + matplotlib         │
                          │   /teams /market /lineups    │
                          │   /budget /digests           │
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
                          │ Cloud Scheduler  │ daily digest
                          └──────────────────┘
```

## 🛠 Operational commands

See [`docs/operations.md`](../../docs/operations.md) for the full reference (build, test, local run, deploy per submodule).

## 💻 Stack at a glance

Python 3.13 · Flask · matplotlib · BeautifulSoup · `requests` · Bazel (`@pypi`) · Cloud Run + Cloud Run Jobs + Cloud Scheduler · Secret Manager · Artifact Registry · Google Drive + Sheets APIs.
