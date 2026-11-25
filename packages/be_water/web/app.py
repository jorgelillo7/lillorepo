"""Be Water — compare Spanish bottled waters and find yours anywhere.

App factory: create the Flask app, wire the shared template globals, and let
each `routes/` module register its endpoints. Behaviour lives in the route
modules; request helpers and rate limiters live in `helpers.py`.
"""

import os

from flask import Flask

from core.web.compress import compress_responses
from core.web.headers import add_security_headers, harden_session_cookie, style_hashes
from core.web.logs import use_json_logging
from core.web.proxy import trust_proxy
from core.web.static import version_static_urls

# These submodules are imported here (not all used directly) so tests can
# patch them via the stable `packages.be_water.web.app.<module>` namespace —
# patching a shared module's attribute reaches the route that imports it too.
from packages.be_water.web import (  # noqa: F401
    aesan,
    auth,
    config,
    helpers,
    label_ocr,
    photos,
    repository,
)
from packages.be_water.web.domain import format_mineral
from packages.be_water.web.routes import add, admin, main, session

template_dir = os.path.join(os.path.dirname(__file__), "templates")
# What the pages may load, and nothing else (docs/gcp.md, CSP). Inline <script>
# and <style> run only with this request's nonce; the offline page, a static
# file, is allowed by the hash of its styles.
CSP = {
    "default-src": ["'self'"],
    "script-src": [
        "'self'",
        "'nonce-{nonce}'",
        "https://accounts.google.com/gsi/client",
    ],
    "style-src": [
        "'self'",
        "'nonce-{nonce}'",
        *style_hashes(
            os.path.join(os.path.dirname(__file__), "static", "offline.html")
        ),
        "https://accounts.google.com/gsi/style",
    ],
    # Google's sign-in script sizes its button through style attributes it
    # writes itself; only attributes are allowed inline, <style> stays nonced.
    "style-src-attr": ["'unsafe-inline'"],
    "font-src": ["'self'"],
    "img-src": ["'self'", "data:", "https://storage.googleapis.com"],
    "frame-src": ["https://accounts.google.com/gsi/"],
    "connect-src": ["'self'", "https://accounts.google.com/gsi/"],
    "manifest-src": ["'self'"],
    "worker-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
}

app = Flask(__name__, template_folder=template_dir)
compress_responses(app)  # first registered, so it runs last
use_json_logging(app)
add_security_headers(app, csp=CSP)
version_static_urls(app)
trust_proxy(app)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
)
harden_session_cookie(app)

app.context_processor(helpers.context_data)
app.add_template_filter(format_mineral, "mineral")

main.register(app)
add.register(app)
session.register(app)
admin.register(app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Loopback only: the Werkzeug debugger executes code for whoever reaches it.
    app.run(debug=True, host="127.0.0.1", port=port)
