import os
import sys

from dotenv import load_dotenv

from core.utils import load_json_secret

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

# --- Competiciones page ---
# One entry per season, holding the spreadsheets that season's competitions
# live in. **Semicolon-separated**, so a season can span several workbooks
# without a code change: 26-27 keeps everything in one, while 25-26 points at
# the two it was already split across, and no history had to be migrated.
#
# Semicolons rather than commas because `gcloud run deploy --set-env-vars`
# splits its own argument on commas — a comma inside a value makes the deploy
# fail with "Bad syntax for dict arg" before the app ever starts. Commas are
# still accepted when reading, for a hand-written local `.env` that never
# goes through gcloud.
#
# What is *inside* a workbook is not configured at all — every tab describes
# itself (see `competiciones.py`). Adding a competition is adding a tab: no
# entry here, no GitHub secret, no deploy. A sheet id per competition per
# season is exactly what left these pages empty for a year.


def _sheet_ids(env_name: str) -> list[str]:
    """Spreadsheet ids from one env var, blanks dropped.

    Split on `;` or `,`: the deploy has to use `;` (see above), but a local
    `.env` written by hand is not going through gcloud and either reads fine.
    """
    raw = os.getenv(env_name) or ""
    return [part.strip() for part in raw.replace(",", ";").split(";") if part.strip()]


COMPETICIONES_SHEETS = {
    "25-26": _sheet_ids("COMPETICIONES_SHEET_IDS_25_26"),
    "26-27": _sheet_ids("COMPETICIONES_SHEET_IDS_26_27"),
}
# Deliberately shorter than the portadas/calendar TTLs: those refresh a feed
# nobody is watching, this one has the organiser reloading to see the score he
# just typed. `/admin` can flush it early.
COMPETICIONES_CACHE_TTL_SECONDS = 300

# --- Special tournaments (Palmarés "Copas especiales") ---
# Winner graphics live in a public bucket; the app builds the URL from
# {slug}/{temporada}.png and the template drops any that 404 (trying .jpg
# first). Uploading a new winner needs no redeploy — only a brand-new cup type
# adds a line here.
SPECIAL_TOURNAMENTS_BUCKET = os.getenv("SPECIAL_TOURNAMENTS_BUCKET", "biwenger")
SPECIAL_TOURNAMENTS = [
    {"slug": "santa-cup", "label": "Copa Santa Claus"},
    {"slug": "castolo-cup", "label": "Copa Castolo"},
]
# The cups started in 25-26; older palmarés seasons never get a graphic, so the
# block is skipped for them (no broken-image flash, no wasted 404s).
SPECIAL_TOURNAMENTS_SINCE = "25-26"


# --- SCRAPER TRIGGER (admin panel) ---
# Used by `/admin/run-scraper` to launch the Cloud Run Job.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")

# --- Application secrets ---
# Prod: FLASK_WEB_CONFIG_JSON bound from Secret Manager in deploy.yml.
# Local dev: SECRET_KEY / ADMIN_PASSWORD env vars (via .env).
_FLASK_CFG = load_json_secret("FLASK_WEB_CONFIG_JSON")

# Refuse to start without a SECRET_KEY in production. A predictable default
# (the old "default-dev-key") makes Flask session cookies trivially forgeable,
# so we never want it to silently leak into a real deploy.
SECRET_KEY = _FLASK_CFG.get("secret_key") or os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules:
        # Test suites set their own value on app.config after import; allow
        # module import to succeed so collection doesn't fail.
        SECRET_KEY = "pytest-secret-key-not-for-prod"
    else:
        raise RuntimeError(
            "SECRET_KEY env var is required; refusing to start with a default."
        )

ADMIN_PASSWORD = _FLASK_CFG.get("admin_password") or os.getenv("ADMIN_PASSWORD")

# --- Deployed version metadata (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- League newspaper covers (Salseo) ---
# The league publishes an occasional front page. They live in the same public
# bucket as the cup graphics, named by the date printed on the masthead —
# the edition numbers the generator prints are not consistent (it went from
# "Año 1 Número 001" to "Año 2 Número 026" in six days), while the dates are.
# An `index.json` alongside them carries date + headline, so publishing a new
# one is two uploads and no deploy. The web only ever reads public URLs; it
# holds no bucket credentials and cannot list.
PERIODICO_BUCKET = os.getenv("PERIODICO_BUCKET", "biwenger")

# --- Non-critical configuration (hardcoded defaults) ---
MESSAGES_PER_PAGE = 7
