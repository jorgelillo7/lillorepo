import os

from dotenv import load_dotenv

from core.utils import load_json_secret

load_dotenv()


# Production: TELEGRAM_BOT_CONFIG_JSON (keys: bot_token, chat_id, webhook_secret)
# Local dev: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / TELEGRAM_WEBHOOK_SECRET fallback.
_TELEGRAM_CFG = load_json_secret("TELEGRAM_BOT_CONFIG_JSON")

TELEGRAM_BOT_TOKEN = (
    _TELEGRAM_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_CHAT_ID = (
    _TELEGRAM_CFG.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
).strip()
TELEGRAM_WEBHOOK_SECRET = (
    _TELEGRAM_CFG.get("webhook_secret") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
).strip()

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "biwenger-tools")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME", "biwenger-teams-analyzer")

# Deployed version metadata (set by CI, see deploy.yml). Used by /version.
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")
