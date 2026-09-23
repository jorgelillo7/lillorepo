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
    """Parse a JSON-object secret from `env_var`.

    Unset or blank returns `{}`: local dev and tests fall back to individual
    env vars. Set but not a JSON object raises `ValueError` naming the variable,
    never its value — a corrupted production secret must fail at startup, not
    turn into empty credentials that fail later somewhere else.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"{env_var} is set but is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"{env_var} is set but is not a JSON object")
    return parsed


def format_euros(n: int | None) -> str:
    """Spanish-style euro formatting: `12.345.678 €`.

    `None` returns `"—"` so callers can tell "Biwenger returned 0" apart
    from "field not present" without an extra branch at every call site.
    """
    if n is None:
        return "—"
    s = f"{int(n):,}".replace(",", ".")
    return f"{s} €"
