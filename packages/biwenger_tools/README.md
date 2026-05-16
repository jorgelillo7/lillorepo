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
| [`teams_analyzer/`](teams_analyzer/README.md) | Cloud Run Job (daily cron + on-demand) | PNG squad/market tables enriched with JP predictions |
| [`telegram_bot/`](telegram_bot/README.md) | Cloud Run Service | Webhook for `/analizar`, `/myteam`, `/mercado`, `/alinear`, `/help` |

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
      │   teams_analyzer (Job)       │
      │                              │
      │  daily cron ──┐              │
      │               ▼              │
      │   matplotlib → PNG → Telegram│
      │   ▲                          │
      └───┼──────────────────────────┘
          │ on /analizar etc.
          │
   user ──┴──▶ telegram_bot (Svc) ──┘ fan-out
```

## 🛠 Operational commands

See [`docs/operations.md`](../../docs/operations.md) for the full reference (build, test, local run, deploy per submodule).

## 💻 Stack at a glance

Python 3.13 · Flask · matplotlib · BeautifulSoup · `requests` · Bazel (`@pypi`) · Cloud Run + Cloud Run Jobs + Cloud Scheduler · Secret Manager · Artifact Registry · Google Drive + Sheets APIs.
