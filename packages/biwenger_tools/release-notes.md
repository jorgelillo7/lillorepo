# Project Release Notes

The incredible, and sometimes chaotic, evolution of our little big project.

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
