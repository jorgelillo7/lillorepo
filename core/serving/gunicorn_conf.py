"""Gunicorn settings shared by every service: its own log lines as JSON.

Plain-text gunicorn lines (worker timeouts, boot failures) reached Cloud
Logging as DEFAULT, invisible to `severity>=ERROR`. This routes them through
the same formatter as `core.utils.get_logger`.

gunicorn merges this dict shallowly over its defaults, whose root logger has
a stdout handler. Root is emptied here: application loggers carry their own
handler and propagate, so a root handler would print every line twice.
"""

from core.utils import LOG_FORMAT

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "INFO", "handlers": []},
    # Replaces gunicorn's `loggers` wholesale, so the error logger is restated.
    # Access lines stay off: any logconfig switches them on, and Cloud Run
    # already writes a request log.
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
            "qualname": "gunicorn.error",
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": [],
            "propagate": False,
            "qualname": "gunicorn.access",
        },
    },
    "formatters": {
        "generic": {"()": "core.utils.CloudLoggingFormatter", "fmt": LOG_FORMAT},
    },
}
