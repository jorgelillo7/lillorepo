import os

from dotenv import load_dotenv

from core.utils import load_json_secret

load_dotenv()


# Production: CHUCKNORRIS_BOT_CONFIG_JSON (keys: bot_token, webhook_secret)
# Local dev: TELEGRAM_BOT_TOKEN / TELEGRAM_WEBHOOK_SECRET fallback.
_CHUCKNORRIS_CFG = load_json_secret("CHUCKNORRIS_BOT_CONFIG_JSON")

TELEGRAM_BOT_TOKEN = (
    _CHUCKNORRIS_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_WEBHOOK_SECRET = (
    _CHUCKNORRIS_CFG.get("webhook_secret") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
).strip()
