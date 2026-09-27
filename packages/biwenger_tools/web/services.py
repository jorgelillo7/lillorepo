"""Google API service initialization for the web app.

Only the Sheets client lives here now — Drive retired with the
Firestore migration. The Sheets API still needs an explicit SA key for
the trofeos / Liga H2H reads (the user shared those
sheets with the SA, not with the Cloud Run compute identity).
"""

from core.sdk.gcp import get_google_service
from core.utils import get_logger
from packages.biwenger_tools.web import config

logger = get_logger(__name__)

sheets_service = None


def init_services() -> None:
    """Initialize the Sheets service as a module-level global."""
    global sheets_service

    try:
        sheets_service = get_google_service("sheets", "v4", config.SCOPES)
    except Exception as e:
        logger.critical(
            "Failed to initialize Sheets service.",
            extra={"error": str(e)},
            exc_info=True,
        )
