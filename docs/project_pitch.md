# Project pitch

> Notes on how to narrate this project in an interview or technical review.

## The positioning line

> "I used a Biwenger project as an excuse to practice Bazel monorepos, cloud-native GCP architecture, and production-grade CI/CD."

That line frames the project correctly: not as a one-off spring side project but as deliberate practice of real-world skills.

---

## Strong points to highlight

**Bazel in a personal project** is the strongest signal. 99% of side projects use a Makefile or just `python app.py`. This repo has bzlmod, custom macros, separate OCI layers, a lockfile with hashes, a pre-compiled base image, and explicit platform definitions.

**Pre-compiled base image** (`Dockerfile.base` with every dep pre-installed) cuts cold-start time. It's a deployment-loop optimisation detail that not everyone thinks of.

**Correct secrets management.** Secret Manager with file mounts in Cloud Run, no sensitive data in env vars, with a local `.env` fallback. Exactly how it's done in production.

**CI/CD with automatic cleanup baked in.** The cleanup script that distinguishes between tagged and untagged multi-arch images in Artifact Registry is a fine detail. Many projects let the registry balloon.

**`DESIGN.md` for a personal project.** Adopts the [Google Labs](https://github.com/google-labs-code/design.md) format for describing design systems to AI agents: colour tokens, typography, and composition rules in YAML + human-readable prose. Most backend devs never document the UI; this format is also the emerging standard for getting agents to apply visual consistency programmatically.

**Properly decoupled data pipeline.** The scraper knows nothing about the web; the web knows nothing about the scraper. The interface used to be the CSV on Drive — now it's Firestore.

---

## Weaknesses to be ready for

**CSV as a database.** The most obvious question. The honest answer works well: "Drive was already in the stack, the dataset is small, the scraper is single-instance by design, and I prioritised simplicity over scalability for this specific case." What you cannot say is that you never thought about it. The Firestore migration is now live.

**JSON inside CSV cells** in `tabla_justicia` (`hechos`, `recibidos`). A sign that the CSV format was being stretched past its limits. Solved by Firestore.

**`TEMPORADA_ACTUAL` duplicated** in `web/config.py` and `scraper_job/config.py` — two independent deployments that can drift out of sync.

**The base image still includes Selenium** (~150MB) by inertia: nobody uses it any more (v4.2 replaced the only dependency with a direct HTTP call to the Jornada Perfecta private API; all that logic now lives in `biwenger-api`). The next `Dockerfile.base` rebuild removes it.

---

## Overall assessment

For a cover-letter signal: solid. Shows that you can build real infrastructure around a Python project: build system, cloud deployment, secrets, CI/CD, tests, documentation. That's already more than 80% of portfolios show.
