"""Google API service initialization for the web app."""
import os

from core.sdk.gcp import get_google_service
from core.utils import get_logger
from packages.biwenger_tools.web import config

logger = get_logger(__name__)

drive_service = None
sheets_service = None


def init_services() -> None:
    """Initialize Google Drive and Sheets services as module-level globals."""
    global drive_service, sheets_service

    sa_path = config.SERVICE_ACCOUNT_PATH
    if not os.path.exists(sa_path):
        base_dir = os.path.dirname(__file__)
        sa_path = os.path.join(base_dir, "biwenger-tools-sa.json")

    try:
        drive_service = get_google_service("drive", "v3", sa_path, config.SCOPES)
        sheets_service = get_google_service("sheets", "v4", sa_path, config.SCOPES)
    except Exception as e:
        logger.critical(
            "Failed to initialize Google services.",
            extra={"error": str(e)},
            exc_info=True,
        )
