# Project pitch

> Notes on how to narrate this project in an interview or technical review.

## The positioning line

> "I used a Biwenger project as an excuse to practice Bazel monorepos, cloud-native GCP architecture, and production-grade CI/CD — then grew it into a multi-product monorepo (a second app, Be Water, on its own GCP project) riding the same machinery."

That line frames the project correctly: not a one-off side project but deliberate practice of real-world skills, and proof the setup scales to a second product without re-inventing the build/deploy/cost machinery. For the current state and capability inventory, point reviewers at `STATUS.md` at the repo root.

---

## Strong points to highlight

**Bazel in a personal project.** 99% of side projects use a Makefile or just `python app.py`. This repo has bzlmod, custom macros (`python_service`), separate OCI layers, a lockfile with hashes, a pre-compiled base image, and explicit platform definitions.

**Pre-compiled base image.** `docker/Dockerfile.base` ships every runtime dep (including `google-cloud-firestore` + `grpcio`) so the per-service images stay small and cold starts stay fast. It's a deployment-loop optimisation detail that not everyone thinks of.

**Correct secrets management.** Secret Manager with file mounts in Cloud Run, no sensitive data in env vars, ADC for Firestore (no key files), with a local `.env` fallback for dev.

**CI/CD with automatic cleanup baked in.** The cleanup script distinguishes between tagged and untagged multi-arch images in Artifact Registry, and the cleanup job runs under a GitHub Actions `concurrency` group so parallel deploys don't race on the same digest.

**Two-tier auto-bid pricing.** The auto-bid engine bids `min(price × multiplier, price + cap)` per tier: the multiplier dominates on cheap players, the absolute cap dominates on expensive ones. With a 0-1000 € jitter on every bid so the trail doesn't look like a bot.

**`DESIGN.md` for a personal project.** Adopts the [Google Labs](https://github.com/google-labs-code/design.md) format for describing design systems to AI agents: colour tokens, typography, and composition rules in YAML + human-readable prose. Most backend devs never document the UI; this format is also the emerging standard for getting agents to apply visual consistency programmatically.

**Properly decoupled data pipeline.** The scraper knows nothing about the web; the web knows nothing about the scraper. The interface is Firestore (deterministic SHA-256 doc IDs, server-side queries with a composite index, TTL policy on the auto-bid log).

**Defensive HTML escaping in the Telegram path.** Every dynamic value flowing into a Telegram HTML message goes through `html.escape`. A `>` in a skip-reason payload silently dropped an auto-bid summary in production on 2026-05-24; the regression test (`test_format_telegram_text_html_escapes_user_content`) pins the fix.

---

## Weaknesses to be ready for

**No staging environment.** Local + prod is enough for one user; every merge ships. The trade-off is articulated in `STATUS.md` under "Accepted gaps".

**Observability stops at Cloud Logging.** No alerts, no dashboards. Same trade-off — observability tooling would push past the sub-euro/mes target.

**Uneven test coverage across products.** The biwenger platform sits at a ~0.60 test/src ratio; `be_water` shipped four productizing sprints fast and lags at ~0.46. Honest answer: known, and it's the reason `STATUS.md` sits at 9.3 rather than the ~9.5 cap.

**Bus factor 1.** Single author/operator for every service, SDK and runbook. Fine for a side project; a real caveat for anything claiming "production maturity".

---

## Overall assessment

For a cover-letter signal: solid. Shows that you can build real infrastructure around a Python project: build system, cross-project cloud deployment, secrets, CI/CD, tests, documentation, and automated reasoning under hard cost constraints — and that the setup scaled to a second product. Current maturity (2026-07-25): **9.3 / 10** (see `STATUS.md` for the full rationale and the ~9.5 cap).
