"""Gzip for the text the Flask apps render: HTML, JSON, JavaScript, CSS and SVG.

Cloud Run does not compress responses, and a season page is 200 KiB of HTML.
Gzip comes from the standard library; brotli would add a dependency to the base
image for a few more percent.
"""

import gzip

from flask import Flask, Response, request

COMPRESSIBLE = (
    "text/html",
    "text/css",
    "text/plain",
    "application/json",
    "text/javascript",
    "application/javascript",
    "application/manifest+json",
    "image/svg+xml",
)
MIN_BYTES = 1024
LEVEL = 6


def compress_responses(app: Flask) -> Flask:
    """Gzip a rendered text response the client accepts gzip for, above 1 KiB."""

    @app.after_request
    def _gzip(response: Response) -> Response:
        if (
            response.direct_passthrough
            or response.is_streamed
            or response.status_code < 200
            or response.status_code in (204, 304)
            or "Content-Encoding" in response.headers
            or response.mimetype not in COMPRESSIBLE
            or "gzip" not in request.headers.get("Accept-Encoding", "").lower()
        ):
            return response
        body = response.get_data()
        response.vary.add("Accept-Encoding")
        if len(body) < MIN_BYTES:
            return response
        response.set_data(gzip.compress(body, compresslevel=LEVEL, mtime=0))
        response.headers["Content-Encoding"] = "gzip"
        # A strong ETag names the uncompressed bytes; these are others.
        etag, weak = response.get_etag()
        if etag and not weak:
            response.set_etag(etag, weak=True)
        return response

    return app
