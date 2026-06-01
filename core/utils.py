import json
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


def load_json_secret(env_var: str) -> dict:
    """
    Reads a JSON-encoded secret from an env var and parses it.
    Returns an empty dict if the var is missing or invalid JSON so callers can
    safely chain `.get(...)` over the result.
    """
    raw = os.getenv(env_var, "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def format_euros(n: int | None) -> str:
    """Spanish-style euro formatting: `12.345.678 €`.

    `None` returns `"—"` so callers can tell "Biwenger returned 0" apart
    from "field not present" without an extra branch at every call site.
    """
    if n is None:
        return "—"
    s = f"{int(n):,}".replace(",", ".")
    return f"{s} €"
