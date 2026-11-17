"""Content-versioned static URLs, so static files can be cached for good.

`url_for('static', filename=...)` gains `?v=<hash of the file>`. A request whose `v`
matches the file on disk is served immutable for a year; any other static request
keeps Flask's revalidation. A changed file gets a new URL, so no browser keeps an
old copy. The hash is read once per file per process: a deploy is a new process.
"""

import hashlib
import os
from functools import lru_cache

from flask import Flask, Response, request

IMMUTABLE = "public, max-age=31536000, immutable"


def version_static_urls(app: Flask) -> Flask:
    """Add the `v` parameter to static URLs and cache matching requests for good."""
    folder = app.static_folder

    @lru_cache(maxsize=256)
    def digest(filename: str) -> str | None:
        if not folder:
            return None
        path = os.path.realpath(os.path.join(folder, filename))
        if not path.startswith(os.path.realpath(folder) + os.sep):
            return None
        try:
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()[:12]
        except OSError:
            return None

    @app.url_defaults
    def add_version(endpoint: str, values: dict) -> None:
        if endpoint == "static" and "filename" in values and "v" not in values:
            version = digest(values["filename"])
            if version:
                values["v"] = version

    @app.after_request
    def cache_versioned(response: Response) -> Response:
        if (
            request.endpoint == "static"
            and response.status_code == 200
            and request.args.get("v")
            and request.args.get("v")
            == digest((request.view_args or {}).get("filename", ""))
        ):
            response.headers["Cache-Control"] = IMMUTABLE
        return response

    return app
