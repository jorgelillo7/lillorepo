import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "biwenger-tools")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME", "biwenger-teams-analyzer")
