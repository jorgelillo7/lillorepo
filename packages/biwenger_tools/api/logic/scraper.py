"""Trigger the scraper Cloud Run Job from the bot.

Thin wrapper over `core.sdk.gcp.trigger_cloud_run_job`. The bot calls
`POST /scraper/trigger`; this returns immediately with the queued
execution name. The scraper itself notifies Telegram when it finishes
(see `packages/biwenger_tools/scraper_job/main.py`).
"""

from core.sdk.gcp import trigger_cloud_run_job
from core.utils import get_logger
from packages.biwenger_tools.api import config

logger = get_logger(__name__)


def run_trigger_scraper() -> dict:
    """Queue an execution of the scraper Cloud Run Job. Returns a summary.

    Does NOT wait for the job to finish — Cloud Run Jobs API returns
    once the execution is queued (a couple of seconds). The scraper's
    own Telegram notify (success or error) closes the loop later.
    """
    execution = trigger_cloud_run_job(
        config.GCP_PROJECT_ID,
        config.CLOUD_RUN_REGION,
        config.SCRAPER_JOB_NAME,
    )
    logger.info("Scraper triggered via api.", extra={"execution": execution})
    return {"queued": True, "execution": execution, "job": config.SCRAPER_JOB_NAME}
