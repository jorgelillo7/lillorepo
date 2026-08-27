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

# Per-season Sheet IDs for the awards pages. Hand-edited in Sheets by the
# league, never moved to Firestore. A season absent from a map did not play
# that competition, and its tab is not rendered.
#
# The Ligas Especiales retired after 25-26 — the league dropped them and the
# Liga H2H took their slot.
TROFEOS_SHEETS = {
    "25-26": os.getenv("TROFEOS_SHEET_ID_25_26"),
}

# Liga H2H (reglamento ch. III). Started in 26-27; a season absent from this
# map never played it, which the page states rather than treating as an error.
# The organiser types two scores per match into this sheet and the site
# follows within `H2H_CACHE_TTL_SECONDS` — no deploy.
H2H_SHEETS = {
    "26-27": os.getenv("H2H_SHEET_ID_26_27"),
}
# Deliberately shorter than the portadas/calendar TTLs: those refresh a feed
# nobody is watching, this one has the organiser reloading to see the score he
# just typed. `/admin` can flush it early.
H2H_CACHE_TTL_SECONDS = 300
# Wide enough to cover the 105 fixtures with room for spare rows; the parser
# locates the block itself, so the range only has to contain it.
H2H_SHEET_RANGE = "A1:H500"

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
