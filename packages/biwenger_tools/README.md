#  Biwenger Tools

## 🔥 Does your Biwenger league drama deserve to live forever? 🔥

Do you enjoy the banter and trash talk between friends that keeps your leagues alive? Does it annoy you when it all gets buried under ads or wiped when the season resets?

Here is the solution! This project is a **backup + web + analysis** system so your most epic messages, legendary feuds, and tactical breakdowns are preserved and accessible. And yes, it was built with more than a little help from AI ;)

---

## 📜 Project Description

This project is split into three main components that work together to archive, visualise, and analyse data from a Biwenger league.

1.  **Message Scraper (`scraper_job`):** An automated Python script that connects to Biwenger, extracts all announcements, categorises them (`comunicado`, `dato`, `cesion`), pre-processes participation data, and saves everything as CSV files in Google Drive.

2.  **Web App (`web-app`):** A lightweight Flask web application that reads data from CSV files and a Google Sheet, presenting it in a clean, elegant, fully responsive interface.

3.  **Teams Analyser (`teams-analyzer`):** A pre-matchday analysis script that pulls squad, market and rival data from the Biwenger API and enriches it with predicted ratings from the Jornada Perfecta private API. The output is a series of formatted Telegram messages — own squad, market top-N, one per rival.

---

## ✨ Key Features

### Message Scraper (The Smart Collector)

* **Secure Authentication:** Logs into Biwenger securely.
* **Smart Categorisation:** Analyses message titles and classifies them automatically.
* **Data Pre-processing:** Generates an optimised `participacion.csv` file so the web app loads statistics instantly.
* **Cloud Storage:** Saves and updates CSV files in Google Drive.
* **Full Automation:** Designed to run as a **Cloud Run Job** scheduled with **Cloud Scheduler**.
* **Secret Management:** All credentials are handled securely through **Google Secret Manager**.

### Web App (The League Portal)

* **Clean Interface:** An elegant, minimalist design with a light theme for perfect readability.
* **Multiple Sections:**
    * **Comunicados:** View official messages with pagination and global search.
    * **Salseo:** A section for "Curiosities" and "Clausulazos".
    * **Participación:** A ranking showing a breakdown of each player's participation.
    * **Palmarés:** A historical summary of past seasons.
    * **Ligas Especiales:** Reads and displays special tournament data directly from a **Google Sheet**.
* **Centralised Config:** Uses a `config.py` file and `.env` for easy management.
* **Cloud Deployed:** Hosted on **Cloud Run** for scalable, efficient performance.

### Teams Analyser (The Tactical Spy)

* **Single HTTP call to Jornada Perfecta:** Reads predicted ratings (the SofaScore-based "Automanager" type=2 rate) for every player in LaLiga in one request. No browser automation, no Selenium.
* **360º Analysis:** Evaluates your own squad, every rival squad, and the free-agent market.
* **Data Enrichment:** Crosses Biwenger data with JP predictions by normalised name + slug; flags injuries, suspensions and players who won't be in the lineup.
* **Telegram Messages:** Posts a series of formatted text messages (HTML, traffic-light status emojis) — own squad, market top-N, one per rival, splitting if any chunk exceeds the 4096-char limit.
* **Local Execution:** Designed to be run manually when you need a deep analysis before a matchday.

---

## 💻 Technologies Used

* **Backend (Scraper Job):** Python, Requests, BeautifulSoup, Unidecode, Google Cloud SDK.
* **Backend (Teams Analyzer):** Python, Requests (Biwenger API + Jornada Perfecta private API), Telegram Bot API.
* **Backend (Web):** Python, Flask.
* **Frontend:** HTML, Tailwind CSS, JavaScript.
* **Cloud & Deployment:** Google Cloud Run (Jobs and Services), Cloud Scheduler, Secret Manager, Google Drive API, Google Sheets API, Docker.


| Action                 | Command                                                              | Description                      |
| ---------------------- | -------------------------------------------------------------------- | -------------------------------- |
| 🧪 Run tests           | `bazel test //packages/biwenger_tools/web:web_tests`                 | Run pytest                       |
| 🏠 Local server        | `bazel run //packages/biwenger_tools/web:web_local`                  | Run on your machine              |
| 🐳 Local image         | `bazel run //packages/biwenger_tools/web:load_image_to_docker_local` | Build and load into Docker       |
| ☁️ Push to GCP         | `bazel run //packages/biwenger_tools/web:push_image_to_gcp`          | Build + Push to Artifact Registry |
| 📦 Clean local image   | `docker run --rm -p 8080:8080 bazel/web:local`                       | Run the image manually           |
