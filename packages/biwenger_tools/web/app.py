"""Biwenger web application."""
import os
import re

from flask import Flask, g, request, session

from packages.biwenger_tools.web import config, services
from packages.biwenger_tools.web.routes.admin import bp as admin_bp
from packages.biwenger_tools.web.routes.main import bp as main_bp
from packages.biwenger_tools.web.routes.season import bp as season_bp

_SEASON_RE = re.compile(r"^\d{2}-\d{2}$")

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY

services.init_services()

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
