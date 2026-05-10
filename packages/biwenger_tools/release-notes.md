# Project Release Notes

The incredible, and sometimes chaotic, evolution of our little big project.

### **v5.1 - El Regreso de Chuck (10 May 2026)**

A bot that first went live on 6 October 2015 — commit message: *"appbot example"* — is back. It spent a decade dormant in a public GitHub repo, originally built to experiment with Node.js, Heroku, and the Telegram Bot API. It now lives in this monorepo, rewritten in Python, deployed on Cloud Run, and sharing the same Bazel infrastructure as everything else. Same jokes. Different everything else.

* **🤜 Chuck Norris Bot resurrected**: New package `packages/chucknorris_bot` — Python/Flask rewrite of the [original 2015 Node.js bot](https://github.com/jorgelillo7/ChuckNorrisJokesBot). Supports `/random`, `/science`, `/food`, `/animal`, `/dev`, `/start` and `/help`. Facts served by [chucknorris.io](https://api.chucknorris.io), secured with Telegram webhook secret validation, deployed on Cloud Run.
* **🌐 Landing page recovered**: The original Bootstrap + jQuery + Angular frontend is gone. In its place: a pure CSS dark-mode landing — near-black background, `CHUCKBOT` in Black Ops One with a red glow, command grid, and an origin card telling the 2015 → 2026 story. No JS, no frameworks, no images.
* **🔑 Webhook secret newline fix**: Cloud Run mounts secrets with a trailing newline; `config.py` now strips both token and webhook secret to avoid silent 401 mismatches on every Telegram update.
* **🎨 DESIGN.md**: Design system documented — colors, typography, component rules — following the same format as `biwenger_tools/web`.

---

### **v5.0 - Bot Interactivo & Alineación Automática (10 May 2026)**

The analyzer grows a brain and a mouth. A dedicated Telegram bot service wires up five commands, and the new `/alinear` engine picks the best eleven for you — backtracking across every formation, respecting positions, injury statuses, and a captain price cap the Biwenger API actually enforces. Teams are now delivered as pixel-perfect PNG tables instead of plain text.

* **🤖 Telegram Bot Service**: A new Flask Cloud Run Service (`telegram_bot`) receives webhooks from Telegram and fans out to Cloud Run Jobs — one per command, one per mode. Validated by `X-Telegram-Bot-Api-Secret-Token`; silently ignores any chat that isn't yours.
* **📋 Five Commands, Zero Friction**: `/analizar` (all squads + market), `/myTeam` (just yours), `/mercado` (market only), `/alinear` (auto-lineup), `/help` (command list). Each sends an immediate ACK ("⏳ recibido, procesando…") so you know the request landed, and reports any Cloud Run error back to the chat.
* **🧠 `/alinear` — Lineup Optimizer**: Backtracking search over 12 formations picks the assignment that maximises total SF predict score. Multi-position players are assigned to their most defensive eligible slot first. Reserve slots follow Biwenger's PT/DF/MC/DL positional order. Captain must have a market value strictly below 3 M€ (excluding unknown-price players) — the API rejects anything else.
* **🖼️ PNG Table Images**: Squad and market tables are now rendered as images with `matplotlib` rather than plain-text messages. Columns auto-fit; colours, fonts, and layout are consistent across every report.
* **🔒 Clausulable Data**: Rival squad tables now include two extra columns — whether the player's clause is currently activatable and for how many days the lock runs. Derived from `owner.clauseLockedUntil` in the Biwenger squad endpoint.
* **🚀 CI Levels Up**: `teams_analyzer` gets its own deploy step in the pipeline. Artifact Registry cleanup now uses `roles/artifactregistry.repoAdmin` (previously `writer`, which lacks delete) — the clean-images script finally runs without PERMISSION_DENIED. GH Actions runners bumped; Python libs upgraded.
* **🧹 Dead Code Purge**: Text/CSV formatting paths that predated the PNG switch are removed. No feature flags, no backwards-compatibility shims — just less code.

---

### **v4.2 - Selenium Goes Home (3 May 2026)**

The teams_analyzer trades its browser for a single HTTP call. Selenium and
Analítica Fantasy are out; the Jornada Perfecta private API is in. Around
that swap come a domain-model rollout, a richer Biwenger SDK, lint in CI,
and a long overdue dead-code purge.

* **🛑 Selenium goes home**: The Selenium + Analítica Fantasy path is gone from `teams_analyzer`. Previously ~600 browser actions to load tables, paginate and read cells; now one request to `https://www.jornadaperfecta.com/api/fitness-daily`. Net: a faster, simpler, fragility-free analyzer.
* **🕵️ Token captured with Frida**: New doc in `docs/technical/reverse-engineering/frida-android-intercept.md` walks through how the JP private API was discovered and how the token was extracted from the Android app's JS bundle. If it ever rotates, recovery is < 1 minute and Frida-free.
* **💬 From CSV file to Telegram messages**: The analyzer no longer ships a CSV via `sendDocument`. It now posts a series of formatted text messages (HTML, traffic-light emoji per player) — own squad, market top-N, one per rival manager, splitting if a chunk exceeds the 4096-char limit.
* **🧱 Domain models applied**: `LeagueMessage`, `Participation`, `Clausulazo` and `JusticeEntry` leave the drawer. Consistent `from_csv_row`/`to_csv_row` on every model; the scraper writes models, the web reads them typed. Makes the eventual Firestore migration a one-layer change instead of touching every call site.
* **🏗️ Biwenger SDK levels up**: Public URL constants, helpers for `league_*` / `manager_squad_url`, and `BiwengerClient.get_all_board_messages()` / `get_all_clausulazos()` (the paginators that used to live as standalone helpers in `scraper_job`). Zero URL duplication between packages.
* **🧹 Tech cleanup**: pytz → stdlib `zoneinfo`; `send_telegram_notification` retired (no callers); three obsolete `*_CSV_URL` env vars purged from the workflow, `BUILD.bazel` and `deploy.sh`; broken `web/Makefile` deleted; gunicorn launcher uses the canonical module path instead of a `sys.path` hack.
* **✅ Lint in CI**: new `flake8` + `black --check` job runs before tests, with versions pinned to the lockfile. Pipeline is now `lint → test → deploy`. Documented in `docs/setup/linter.md`.
* **🧪 Tests with less posturing**: audit of the 12 test files → 4 removed (assertions on "the method was called" rather than outcomes), 8 hardened to verify content instead of just the method calls, 9 new ones covering error paths the old suite never touched (auth raises, JP unreachable, JP fetch fails mid-flow, empty squad, price-increment branches).

---

### **v4.1 - The Clausulazo Hunter (25 April 2026)**

The Salseo gets smarter. Clausulazos — those jaw-dropping transfer fees that shake the league — are now a first-class citizen: detected by the scraper, processed with proper logic, and showcased in their own section of the web. A round of refactors and a translation sprint round out the release.

* **🌶️ New "Clausulazos" Section in Salseo**: Cesiones is out, Clausulazos is in. The Salseo page now features a dedicated section to highlight the biggest transfer fees in the league, with a fresh UI to match.
* **🔄 Clausulazos Logic Moves to the Scraper**: Detection and processing of clausulazo messages is extracted from the web and moved into `scraper_job/logic/processing.py`, where it belongs. The web now just displays what the scraper has already classified — cleaner, faster, and properly tested.
* **🧪 New Processing Tests**: The new `logic/processing.py` module comes with a full test suite (`test_processing.py`), ensuring clausulazo detection is reliable across edge cases.
* **🏗️ Web Bazel Refactor**: The web's `BUILD.bazel` is slimmed down significantly. A new `Makefile` and `entrypoint.sh` are introduced to simplify local development and container startup, reducing the cognitive overhead of working with the web module.
* **🌍 Docs Now in English**: All READMEs and documentation across the project have been translated to English, making the codebase more accessible and consistent.

---

### **v4.0 - Welcome, Mr. Bazel (30 September 2025)**

A total re-architecture that transforms the project into a **monorepo** managed by **Bazel**, Google's build system. Was it necessary? Not really. Did we want to push cutting-edge technology and see how far we could take it? Absolutely. This change lays the foundation for a faster, more scalable, and more professional project than ever.

* **🧱 Unified Monorepo**: Goodbye to separate modules! All the code (`core`, `web`, `scraper_job`, `teams_analyzer`) now lives in a single repository. This simplifies dependency management and ensures total consistency across the project.
* **🚀 Ultra-fast Builds and Tests**: **Bazel** is implemented to manage builds, testing, and deployments. Thanks to its advanced cache system, only what has actually changed is rebuilt and retested, drastically reducing wait times.
* **📦 Dependencies: The Best of Both Worlds**: A hybrid dependency system is adopted. For local development and testing, Bazel uses its internal graph (`@pypi//...`) for maximum speed and hermetic builds. For the final Docker image, a more traditional and robust approach is used: packaging `requirements_lock.txt` and running `pip install` on container startup. This gives us the reproducibility of a lock file and the universal compatibility of pip, avoiding complex packaging issues.
* **🐳 Docker Images with Bazel**: Traditional `Dockerfile`s are replaced by `oci_image` rules inside Bazel. Image definitions now live alongside the source code, creating a fully integrated and consistent workflow.
* **🧹 Cleanup and Consolidation**: Redundant config files (`pyproject.toml`, `Dockerfile` in migrated modules) are removed to consolidate `BUILD.bazel` as the single source of truth.
* **🌱 From Project to Platform: The Monorepo Expands**: With the power and scalability of Bazel, the repository is no longer exclusive to Biwenger. The current architecture becomes a **robust, reusable template** for launching new projects of any kind, leveraging all the established infrastructure, dependency management, and GCP deployment. The logical next step: turning this project into a hub for future ideas and experiments.

---

### **v3.2 - The Tireless Verifier (5 September 2025)**

A vital update for project robustness, introducing a complete testing system to guarantee code reliability and the stability of existing features.

  * **🧪 A step further in code quality:** A **solid unit testing system** is implemented using **`pytest`** across all modules (`core`, `scraper_job`, `teams_analyzer`, `web`). This ensures every project component works as expected.
  * **🛡️ Comprehensive coverage:** Tests include validation of the Biwenger client, Google Cloud services, data processing, scraper logic, and web application endpoints.
  * **✅ Improved workflow:** With tests in place, we can introduce new features and refactor code with full confidence, knowing any regression will be caught automatically.
  * **🎉 We finally have tests!** A major milestone for the project, bringing us closer to more professional and sustainable development practices.
    A project without tests... it felt wrong :O, better late than never (even if the tests were AI-assisted)


---

### **v3.1 - The Definitive Sync (3 September 2025)**

An update that consolidates the project architecture and simplifies the development workflow, eliminating the most common configuration errors and laying the groundwork for future expansions.

* **⚙️ Unified Development Environment**: The Python virtual environment is centralised to a single `venv` at the project root. This crucial change resolves dependency conflicts between modules and ensures the linter, formatter, and interpreter all work consistently.
* **📦 Simplified Dependency Management**: By consolidating the `venv`, installation commands are simplified, removing the need to activate and deactivate multiple environments. All dependencies are now installed in one place, improving consistency.
* **✅ Local and Cloud Continuous Integration**: Execution, image building, and deployment processes have been verified and optimised for all modules (`web`, `scraper_job`, `teams_analyzer`), ensuring they work seamlessly in both local (Docker) and Google Cloud Platform environments. (minus teams_analyzer)
* **🔗 Consistent Imports and Code Style**: `core` module imports and code style rules with **Flake8** and **Black** have been validated, ensuring the project maintains its quality and cohesion across new features.

---

### **v3.0 - The Tactical Spy and the Architect (22 August 2025)**

A major update that not only introduces a new analysis tool but also rebuilds the project's foundations to make it more robust and scalable.

* **🚀 New `teams-analyzer` Module**: A new standalone tool for deep tactical analysis of the league, designed to be run locally.
* **🕵️ Advanced Scraping with Selenium**: The analyser extracts performance data and coefficients from specialist sites like "Analítica Fantasy" and "Jornada Perfecta".
* **📊 360º Analysis**: The script evaluates all league squads and free agents on the market, providing a complete view of the competition.
* **📬 Telegram Notifications**: On completion, the script automatically sends the `analisis_biwenger.csv` report to a configured Telegram chat.
* **🏗️ Major Architectural Refactor**: A key milestone! A deep code restructuring creates reusable modules in the `core` directories (for API clients like Biwenger and Google) and `logic` (for data processing). This change drastically reduces code duplication, improves maintainability, and lays the foundation for future project expansions.

---

### **v2.5 - The Time Traveller (18 August 2025)**

A fundamental update that turns the web into a historical archive, allowing smooth and intuitive navigation between different seasons.

* **✈️ Multi-Season Navigation:** The star feature! A dropdown menu in the header lets you select and view data (`Comunicados`, `Salseo`, `Participación`, `Ligas Especiales`) from any past season.
* **💾 Multi-Season Scraper:** The `get_messages.py` script is now season-aware. It generates and updates CSV files with a season suffix (e.g. `comunicados_25-26.csv`), keeping each year's data perfectly isolated and preserved.
* **⚖️ New "Fair Play" Section:** A complete rules page is created with a navigable index, dynamic content (like the Special Leagues list), and an improved layout for reading the rules.
* **🖥️ Improved Admin Panel:** The "VAR (Admin)" section now shows the status of files for the season currently being viewed and warns if any dynamic files have not been updated for more than 7 days.
* **📱 UI/UX Improvements:** Navigation menu display on mobile devices is fixed to prevent text being cut off or overlapping, and dropdown menu positioning issues are resolved.


### **v2.0 - The Definitive Portal (12 August 2025)**

A key re-architecture to make the project more robust, secure, and easy to maintain — laying the foundations for the future.

* **🚀 (Beta) New "Special Leagues" Section:** The most anticipated feature. The web can now read and display data from special competitions directly from a **Google Sheet**, allowing extremely simple manual management and updates.
* **⚙️ Configuration Externalisation:** Both the scraper and the web app now use a `config.py` file to manage their parameters. Sensitive credentials and data are loaded securely from a `.env` file locally or from Secret Manager / environment variables in the cloud.
* **🐛 Stability Fixes:** Bugs related to message categorisation and date sorting are resolved, ensuring data is always processed and displayed correctly.

### **v1.5 - The Intelligent Portal (12 August 2025)**

A massive update focused on data intelligence and feature expansion, making the web faster and more complete.

* **✨ New Message Categorisation:** The script now analyses announcement titles and classifies them automatically as `comunicado`, `dato`, or `cesion`, adding a new column to the CSV.
* **⚡️ Participation Optimisation:** A new file, `participacion.csv`, is generated automatically by the scraper. The web now reads this pre-processed file, making the "Participación" tab load instantly.
* **🌶️ New "Salseo" Section:** A new page is created dedicated to "Curious Facts" (Mr. Lucen) and "Clausulazos", with filters to switch between both categories.
* **📊 Improved Participation Table:** The participation section is completely redesigned to show a detailed breakdown of the number of announcements, facts, and clausulazos per player.
* **📄 Pagination on the Home Page:** A pagination system is implemented on the "Comunicados" section to handle a large volume of messages in an orderly way.
* **🔍 Global Search:** The search bar on the home page and "Salseo" now searches across all messages, not just those visible on the current page.

### **v1.0 - The Automaton (07 August 2025)**

The definitive version (for now)! The project reaches maturity with full automation and a professional architecture.

* **✨ Full Automation!** The data collection script is now a **Cloud Run Job**, scheduled to run automatically every week with **Cloud Scheduler**. No more manual runs!
* **🔒 Maximum Security:** All sensitive credentials (Biwenger, Google Drive) have been moved to **Google Secret Manager**. The code is clean of secrets.
* **🏗️ Decoupled Architecture:** The project is officially split into two parts: the **automated scraper** (the job) and the **web application**, each with its own lifecycle.
* **🐛 Bug Fixes:** Permissions and `gcloud` configuration errors are resolved for a robust deployment.

### **v0.5 - The Portal (06 August 2025)**

The web application evolves from a simple page to a complete portal for the league.

* **🎨 New Design:** A cleaner, more elegant visual theme is implemented, improving readability on all devices.
* **📊 New "Participación" Section:** A page is added showing a ranking of announcements published by each participant, with a sortable table.
* **🏆 New "Palmarés" Section:** A section is created to show the history of winners, podiums, and other curiosities from past seasons, read from a second CSV file.
* **🐛 Data Fixes:** Logic to correctly identify announcement authors is improved and formatting issues in the Palmarés section are resolved.

### **v0.4 - Cloud Connection (05 August 2025)**

A crucial step: we separate the data from the application to make the system more flexible and scalable.

* **☁️ Google Drive Integration:** The Python script is modified to upload the `biwenger_comunicados.csv` file to a Google Drive folder.
* **🌐 Cloud Reading:** The Flask application now reads data directly from a public CSV URL in Google Drive, instead of a local file.
* **🚀 Deployment Preparation:** The web application is containerised with **Docker** and prepared for deployment on **Cloud Run**.

### **v0.3 - The Museum (04 August 2025)**

The first visual interface is born for reading announcements in a friendlier way than a plain CSV.

* **🐍 The Web is Born:** A basic web application is created with **Flask**.
* **🎨 First Interface:** An HTML template is designed with **Tailwind CSS** to display announcements in cards.
* **🔍 Search Functionality:** A JavaScript search bar is added to filter announcements in real time.

### **v0.2 - The Collector (03 August 2025)**

The script evolves into a functional backup tool.

* **💾 CSV Saving:** The script now saves all extracted data (date, title, author, content) to a `biwenger_comunicados.csv` file.
* **🔄 Update Logic:** The script becomes smart: it reads the existing CSV and adds only new announcements, keeping the file always up to date and sorted.
* **🆔 Unique ID:** A hash system is implemented to assign a unique ID to each announcement, preventing duplicates.

### **v0.1 - The Spark (02 August 2025)**

The origin of everything. A single Python script with a clear goal.

* **🔑 Login:** The script can authenticate with Biwenger using local credentials.
* **📊 Basic Extraction:** It connects to the Biwenger internal API to obtain basic league data, such as the name and number of participants.
* **💻 Console Output:** All information is displayed directly in the terminal.
