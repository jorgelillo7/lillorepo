import os
import sys

from dotenv import load_dotenv

# Pulls vars from a local .env when present (used for local dev).
load_dotenv()

# --- GOOGLE SHEETS SERVICE ACCOUNT ---
# Mounted from Secret Manager in Cloud Run. Only the Sheets API uses it
# (Drive retired with the Firestore migration).
SERVICE_ACCOUNT_PATH = "/gdrive_sa/biwenger-tools-sa.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


# --- Season configuration ---
# To roll over a season: bump TEMPORADA_ACTUAL in deploy.yml (global env)
# or via: gcloud run services update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "26-27")
# Prepend the new season at the start of each year (see docs/operations.md).
TEMPORADAS_DISPONIBLES = ["24-25", "25-26", "26-27"]

# Per-season Sheet IDs for the Lloros Awards pages. Hand-edited in Sheets
# by the user, never moved to Firestore.
LIGAS_ESPECIALES_SHEETS = {
    "25-26": os.getenv("LIGAS_ESPECIALES_SHEET_ID_25_26"),
}

TROFEOS_SHEETS = {
    "25-26": os.getenv("TROFEOS_SHEET_ID_25_26"),
}


# --- SCRAPER TRIGGER (admin panel) ---
# Used by `/admin/run-scraper` to launch the Cloud Run Job.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")

# --- Application secrets ---
# Refuse to start without a SECRET_KEY in production. A predictable default
# (the old "default-dev-key") makes Flask session cookies trivially forgeable,
# so we never want it to silently leak into a real deploy.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules:
        # Test suites set their own value on app.config after import; allow
        # module import to succeed so collection doesn't fail.
        SECRET_KEY = "pytest-secret-key-not-for-prod"
    else:
        raise RuntimeError(
            "SECRET_KEY env var is required; refusing to start with a default."
        )

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- Deployed version metadata (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- Non-critical configuration (hardcoded defaults) ---
MESSAGES_PER_PAGE = 7
