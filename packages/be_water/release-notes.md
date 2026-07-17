# Be Water — Release Notes

Every drop of progress, documented. 💧

### **v1.0 - Be Water, My Friend (18 July 2026)**

Born from a real problem: away from home, if Lanjarón or Solán de Cabras aren't on the shelf, you pick blind — and sometimes Bezoya happens. From a June README to a public URL in 48 hours: an open catalog of Spanish mineral waters that knows which local water matches your taste, wherever you are.

* **💧 The catalog (the headline)**: 25 Spanish waters across 17 provinces in Firestore, each with its full mineral vector (residuo seco, bicarbonates, chlorides, sulfates, Ca/Mg/Na/K, silica, pH) and its provenance (spring + province + community, cross-checked with the AESAN official list). Cards are color-coded by EU mineralization class — sky for *muy débil* (Bezoya territory), teal for *débil*, amber for *fuerte*, rose for Vichy Catalán energy 🫧.
* **📍 "Estoy de viaje" — the geo-recommender**: mark your favorites, pick where you are, and the app ranks the local waters by distance to your mineral profile. Favorites = Lanjarón + Solán in Girona → it suggests Aigua de Ribes, never Vichy — same province, opposite water.
* **🧮 Similarity engine**: weighted log-scale euclidean distance over the mineral vector (TDS ×2, sodium ×1.5 — log because 100 mg means nothing in TDS and everything in sodium). k-NN in memory, no vector DB, no nonsense. Every water page shows "si no la encuentras, prueba…" with its 3 closest siblings.
* **🍼 First label-verified waters**: two real bottle photos (from a supermarket queue!) became data — Aquadeus corrected against its actual label (the seeded approximation was off by 15%) and Valtorre (Toledo, minero-medicinal since 1972) added from scratch. Claude played interim OCR; Gemini takes the job in v1.1.
* **🔁 Idempotent catalog sync**: `catalog_sync` merges the in-repo dataset into Firestore — creates the missing, updates the unverified (preserving user photos and authorship), never touches a bottle-verified water. Summary lands on Telegram via @be_water_app_bot. Ready to become a monthly scheduled job.
* **☁️ Own GCP project, shared machinery**: `be-water-app` project (isolated Firestore free tier, €1 budget alert) deployed from the lillorepo monorepo — same `python_service` Bazel macro, same `core/` SDKs, same CI, keyless cross-project deploy via the shared WIF service account. Zero new dependencies; secrets consolidated into a single JSON version to stay exactly at the Secret Manager free tier (6/6 across the billing account).
* **🎨 Design system from day one**: `DESIGN.md` documents the mineralization tone system, Inter-only typography and the one rule that matters: *if a screenshot would look bad on a timeline, it's not done*.
* **🔎 Ready to be found**: per-page meta + OG tags, robots.txt, dynamic sitemap.xml, semantic markup, mobile-first. Nickname-only login for the friends phase — Google Sign-In queued for the public jump.
