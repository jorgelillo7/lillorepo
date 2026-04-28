import logging
import os

from pythonjsonlogger import jsonlogger


def get_logger(name: str) -> logging.Logger:
    """
    Returns a logger that emits JSON to stdout.
    Cloud Logging picks up structured JSON automatically, giving
    searchable fields (severity, message, logger name) instead of
    plain text lines.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def read_secret_from_file(secret_path: str, fallback=None):
    """
    Reads a secret mounted as a file (typical in Cloud Run / Secret Manager).
    Falls back to the provided default if the path does not exist.
    """
    if secret_path and os.path.exists(secret_path):
        with open(secret_path, "r") as f:
            return f.read().strip()
    return fallback
