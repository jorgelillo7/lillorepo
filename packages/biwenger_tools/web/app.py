"""Biwenger web application."""

import os
import re

from flask import Flask, g, request, session

from packages.biwenger_tools.web import config, services
from core.web.csrf import get_csrf_token
from packages.biwenger_tools.web.routes.admin import bp as admin_bp
from packages.biwenger_tools.web.routes.main import bp as main_bp
from packages.biwenger_tools.web.routes.season import bp as season_bp
from packages.biwenger_tools.web.sanitize import safe_html

_SEASON_RE = re.compile(r"^\d{2}-\d{2}$")

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY
# Session cookie hardening. SESSION_COOKIE_SECURE defaults to True so HTTPS
# is enforced in Cloud Run; local dev over plain HTTP can set
# SESSION_COOKIE_SECURE=false in .env.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
)

services.init_services()

# Register the sanitize filter so templates can do `{{ msg.contenido | safe_html }}`
# instead of the unsafe `| safe`.
app.jinja_env.filters["safe_html"] = safe_html

app.register_blueprint(main_bp)
app.register_blueprint(season_bp)
app.register_blueprint(admin_bp)


@app.context_processor
def inject_globals() -> dict:
    """Inject common variables into all templates automatically."""
    return {
        "season": g.get("season", config.TEMPORADA_ACTUAL),
        "temporada_actual": config.TEMPORADA_ACTUAL,
        "temporadas_disponibles": config.TEMPORADAS_DISPONIBLES,
        "git_commit": config.GIT_COMMIT,
        "deploy_time": config.DEPLOY_TIME,
        "csrf_token": get_csrf_token,
    }


@app.before_request
def manage_season() -> None:
    """Persist and propagate the active season across requests."""
    if request.endpoint == "static" or request.path.endswith(".ico"):
        return

    if "current_season" not in session:
        session["current_season"] = config.TEMPORADA_ACTUAL

    season_from_url = request.view_args.get("season") if request.view_args else None
    if season_from_url and _SEASON_RE.match(season_from_url):
        session["current_season"] = season_from_url

    g.season = session["current_season"]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
