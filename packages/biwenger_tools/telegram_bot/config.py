import json
import os

from dotenv import load_dotenv

load_dotenv()


def _load_json_secret(env_var: str) -> dict:
    raw = os.getenv(env_var, "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


_TELEGRAM_CFG = _load_json_secret("TELEGRAM_BOT_CONFIG_JSON")

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
