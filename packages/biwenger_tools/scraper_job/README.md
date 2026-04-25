# 🤖 Biwenger Message Scraper

Automated scraping job that extracts announcements (messages) from your Biwenger league and saves them as CSV files. The primary goal is building a data history that can be consumed by other tools.

Data is saved to CSV files and synced directly to a Google Drive folder for easy access.

## 🚀 Key Features

* **Data extraction**: Automatically collects important messages from your Biwenger league feed.
* **CSV storage**: Organises extracted data into a structured format.
* **Google Drive sync**: Uploads generated CSV files to a specific folder in your Google Drive.

## ⚙️ Configuration and Usage

For detailed setup instructions, see the main operations document.

* **Installation and dependencies**: See section **`1.2 Scraper Job`** in `operations.md`.
* **Google API setup**: Follow the Google API credential setup steps.
* **Running and deploying**: Local execution and GCP deployment commands are in `operations.md` **`2.2 Scraper Job`**.

---

### **Google API Setup (First time only, if using OAuth)**

If you want the script to create CSVs directly in your **personal Drive** automatically:

* **Configure the Consent Screen:**

  * Go to **Google Cloud Console** > **APIs & Services** > **OAuth consent screen**.
  * Select **External**, fill in your app details, and add your email as a test user.

* **Create Credentials:**

  * In **APIs & Services** > **Credentials**, click **+ CREATE CREDENTIALS** > **OAuth client ID**.
  * Select **Desktop application**.
  * Download the JSON file and rename it to `client_secrets.json` in the scraper folder.

* **Configure the Drive Folder:**

  * Create a folder in your Google Drive for the CSV files.
  * Copy the folder ID from the URL and paste it into the scraper's `.env` file.

> ⚠️ Note: This flow lets the script write to your personal Drive, but **the OAuth token expires and refreshing it is cumbersome**. That is why we use a **Service Account** instead, which never expires.
> ⚠️ Limitation: Since your account is not Google Workspace, the Service Account **cannot create files directly in your personal Drive**. To make it work, **you must manually create empty CSV files in the Drive folder before running the scraper**.

---

## ⚠️ Important Notes

* **First local run**: Requires manual browser authorisation to access Google Drive (only if using OAuth).
* **Security**: Never commit the `biwenger-tools-sa.json` file to the repository.
