#  Biwenger Tools

## 🔥 Does your Biwenger league drama deserve to live forever? 🔥

Do you enjoy the banter and trash talk between friends that keeps your leagues alive? Does it annoy you when it all gets buried under ads or wiped when the season resets?

Here is the solution! This project is a **backup + web + analysis** system so your most epic messages, legendary feuds, and tactical breakdowns are preserved and accessible. And yes, it was built with more than a little help from AI ;)

---

## 📜 Project Description

This project is split into three main components that work together to archive, visualise, and analyse data from a Biwenger league.

1.  **Message Scraper (`scraper_job`):** An automated Python script that connects to Biwenger, extracts all announcements, categorises them (`comunicado`, `dato`, `cesion`), pre-processes participation data, and saves everything as CSV files in Google Drive.

2.  **Web App (`web-app`):** A lightweight Flask web application that reads data from CSV files and a Google Sheet, presenting it in a clean, elegant, fully responsive interface.

3.  **Teams Analyser (`teams-analyzer`):** A powerful analysis script that uses Selenium to scrape advanced data from fantasy analysis sites. It combines this information with Biwenger data to generate a detailed CSV report and send it via Telegram.

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

* **Advanced Scraping:** Uses **Selenium** to extract data from sites like "Analítica Fantasy" and "Jornada Perfecta".
* **360º Analysis:** Evaluates not just your team but every squad in the league and free agents on the market.
* **Data Enrichment:** Crosses Biwenger data with external metrics like performance coefficients and expected scores.
* **Telegram Notifications:** Sends the final CSV report directly to a Telegram chat so you have the tactical edge on your phone.
* **Local Execution:** Designed to be run manually when you need a deep analysis before a matchday.

---

## 💻 Technologies Used

* **Backend (Scrapers):** Python, Requests, BeautifulSoup, **Selenium**, Unidecode, Google Cloud SDK.
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
