"""Be Water — compare Spanish bottled waters and find yours anywhere.

App factory: create the Flask app, wire the shared template globals, and let
each `routes/` module register its endpoints. Behaviour lives in the route
modules; request helpers and rate limiters live in `helpers.py`.
"""

import os

from flask import Flask

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
from packages.be_water.web.routes import add, admin, main, session

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
)

app.context_processor(helpers.context_data)

main.register(app)
add.register(app)
session.register(app)
admin.register(app)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
