# 🤖 Biwenger Message Scraper

Cloud Run Job that extracts announcements from the Biwenger league board
and writes them to Firestore. Builds the data history that the web app
(and any future consumer) reads.

## 🚀 Key features

* **Board extraction**: pulls every message from the league board on each run.
* **Firestore-native storage**: writes to `comunicados/{season}/messages` and
  derives `participacion`, `clausulazos`, `tabla_justicia` collections.
* **Idempotent**: doc ids are deterministic content hashes; re-running the
  scraper rewrites the same documents (no duplicates).

## 🗺️ Entry point

`main.py` orchestrates the whole job: read existing message ids from
Firestore → fetch the Biwenger board → diff new messages → wipe + bulk
write `comunicados`, `participacion`, `clausulazos`, `tabla_justicia`.
Pure-function processing lives in `logic/processing.py`.

Schemas, indexes, and read costs are documented in `docs/firestore.md`.

## ⚙️ Configuration and usage

* **Installation and dependencies**: see section **`1.2 Scraper Job`** in
  `docs/operations.md`.
* **Local run + GCP deploy**: see **`2.2 Scraper Job`** in
  `docs/operations.md`.
* **Auth**: Application Default Credentials. In Cloud Run the compute SA
  is picked up automatically; locally, run
  `gcloud auth application-default login` once.
