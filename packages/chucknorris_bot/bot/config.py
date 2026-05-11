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


_CHUCKNORRIS_CFG = _load_json_secret("CHUCKNORRIS_BOT_CONFIG_JSON")

TELEGRAM_BOT_TOKEN = (_CHUCKNORRIS_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
TELEGRAM_WEBHOOK_SECRET = (_CHUCKNORRIS_CFG.get("webhook_secret") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "")).strip()
