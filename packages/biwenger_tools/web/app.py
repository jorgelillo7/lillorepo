import os
import pytz
import ssl
from collections import defaultdict
from datetime import datetime, timedelta
from dateutil import parser
from flask import (
    Flask,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
    g,
    jsonify,
)

from packages.biwenger_tools.web import config
from core.sdk.gcp import (
    get_google_service,
    find_file_on_drive,
    download_csv_as_dict,
    get_sheets_data,
)
from core.utils import get_file_metadata

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY

# --- INICIALIZACIÓN DE SERVICIOS ---
# Se inicializan una vez al arrancar la app para reutilizarlos en todas las rutas.
drive_service = None
sheets_service = None
try:
    # Construct paths relative to the current file
    base_dir = os.path.dirname(__file__)
    service_account_path = os.path.join(base_dir, "biwenger-tools-sa.json")
    if os.path.exists(config.SERVICE_ACCOUNT_PATH):
        service_account_path = config.SERVICE_ACCOUNT_PATH

    drive_service = get_google_service(
        "drive", "v3", service_account_path, config.SCOPES
    )
    sheets_service = get_google_service(
        "sheets", "v4", service_account_path, config.SCOPES
    )

except Exception as e:
    # Log critical error if services fail to initialize
    print(f"CRITICAL ERROR: No se pudieron inicializar los servicios de Google: {e}")


# --- REQUEST HANDLERS ---
@app.before_request
def manage_season():
    """
    Gestiona de forma centralizada la temporada seleccionada en todas las peticiones.
    Esto asegura que una vez que se elige una temporada, esta persiste en la sesión
    y se utiliza incluso en páginas que no tienen la temporada en su URL (como /admin).
    """
    if request.endpoint == "static" or request.path.endswith(".ico"):
        return

    # La fuente de verdad definitiva para la temporada actual es la sesión.
    # La inicializamos con un valor por defecto si no existe.
    if "current_season" not in session:
        session["current_season"] = config.TEMPORADA_ACTUAL

    # Si la URL visitada incluye una temporada (ej: /25-26/comunicados),
    # y tiene un formato válido, actualizamos la sesión para reflejar esta nueva selección.
    season_from_url = request.view_args.get("season") if request.view_args else None
    # AÑADIMOS UNA VALIDACIÓN: Solo aceptamos la temporada de la URL si parece válida (contiene un guion).
    # Esto evita que peticiones como /favicon.ico o /robots.txt sobrescriban la sesión.
    if season_from_url and "-" in season_from_url:
        session["current_season"] = season_from_url

    # Finalmente, establecemos g.season a partir del valor de la sesión.
    # g.season será utilizado por todas las rutas durante esta única petición.
    g.season = session["current_season"]


# --- RUTAS DE LA APLICACIÓN ---


@app.route("/favicon.ico")
@app.route("/favicon.ico/")  # CORRECCIÓN: Maneja la ruta con y sin la barra al final.
def favicon():
    """
    Evita que la petición del favicon sea interpretada como una temporada.
    Devuelve una respuesta vacía para que el navegador no muestre un error.
    """
    return "", 204


@app.route("/")
def home():
    """Redirects to the default season's announcements page."""
    return redirect(url_for("comunicados", season=g.season))


@app.route("/<season>/")
def comunicados(season):
    """Displays paginated announcements for a given season."""
    error = None
    paginated_messages = []
    page = 1
    total_pages = 1
    comunicados_only = []
    try:
        if not drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        filename = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
        file_metadata = find_file_on_drive(
            drive_service, filename, config.GDRIVE_FOLDER_ID
        )
        if not file_metadata:
            raise FileNotFoundError(
                f"El archivo '{filename}' no se encontró en Google Drive."
            )

        all_messages = download_csv_as_dict(drive_service, file_metadata["id"])

        comunicados_only = [
            m for m in all_messages if m.get("categoria", "").strip() == "comunicado"
        ]

        page = request.args.get("page", 1, type=int)
        start = (page - 1) * config.MESSAGES_PER_PAGE
        end = start + config.MESSAGES_PER_PAGE

        paginated_messages = comunicados_only[start:end]
        total_pages = (
            len(comunicados_only) + config.MESSAGES_PER_PAGE - 1
        ) // config.MESSAGES_PER_PAGE
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al cargar los comunicados de la temporada {g.season}: {e}"
        print(error)

    return render_template(
        "index.html",
        messages=paginated_messages,
        all_comunicados=comunicados_only,
        error=error,
        active_page="comunicados",
        current_page=page,
        total_pages=total_pages,
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/<season>/salseo")
def salseo(season):
    """Displays various categories of content for a given season."""
    error = None
    datos_curiosos = []
    cesiones = []
    cronicas = []
    try:
        if not drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        filename = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
        file_metadata = find_file_on_drive(
            drive_service, filename, config.GDRIVE_FOLDER_ID
        )
        if not file_metadata:
            raise FileNotFoundError(
                f"El archivo '{filename}' no se encontró en Google Drive."
            )

        all_messages = download_csv_as_dict(drive_service, file_metadata["id"])

        datos_curiosos = [
            m for m in all_messages if m.get("categoria", "").strip() == "dato"
        ]
        cesiones = [
            m for m in all_messages if m.get("categoria", "").strip() == "cesion"
        ]
        cronicas = [
            m for m in all_messages if m.get("categoria", "").strip() == "cronica"
        ]
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al cargar los datos de la temporada {g.season}: {e}"
        print(error)

    return render_template(
        "salseo.html",
        datos=datos_curiosos,
        cesiones=cesiones,
        cronicas=cronicas,
        error=error,
        active_page="salseo",
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/<season>/participacion")
def participacion(season):
    """Displays participation statistics for a given season."""
    error = None
    stats = []
    try:
        if not drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        filename = f"{config.PARTICIPACION_FILENAME_BASE}_{g.season}.csv"
        file_metadata = find_file_on_drive(
            drive_service, filename, config.GDRIVE_FOLDER_ID
        )
        if not file_metadata:
            raise FileNotFoundError(
                f"El archivo '{filename}' no se encontró en Google Drive."
            )

        participation_data = download_csv_as_dict(drive_service, file_metadata["id"])

        for row in participation_data:
            comunicados_count = (
                len(row.get("comunicados", "").split(";"))
                if row.get("comunicados")
                else 0
            )
            datos_count = (
                len(row.get("datos", "").split(";")) if row.get("datos") else 0
            )
            cesiones_count = (
                len(row.get("cesiones", "").split(";")) if row.get("cesiones") else 0
            )
            cronicas_count = (
                len(row.get("cronicas", "").split(";")) if row.get("cronicas") else 0
            )

            stats.append(
                {
                    "autor": row["autor"],
                    "comunicados": comunicados_count,
                    "datos": datos_count,
                    "cesiones": cesiones_count,
                    "cronicas": cronicas_count,
                    "total": comunicados_count
                    + datos_count
                    + cesiones_count
                    + cronicas_count,
                }
            )
        stats.sort(key=lambda item: item["total"], reverse=True)
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al calcular las estadísticas de la temporada {g.season}: {e}"
        print(error)

    return render_template(
        "participacion.html",
        stats=stats,
        error=error,
        active_page="participacion",
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/<season>/lloros-awards")
def lloros_awards(season):
    error = None
    leagues = []
    trofeos = []

    try:
        if not sheets_service:
            raise Exception("El servicio de Google Sheets no está disponible.")

    except Exception as e:
        error = f"Ocurrió un error al cargar los datos: {e}"
        print(error)

    return render_template(
        "lloros_awards.html",
        leagues=None,
        trofeos=None,
        error=error,
        season=season,
        active_page="lloros_awards",
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/api/lloros-awards/ligas")
def api_lloros_ligas():
    error = None
    leagues = []
    try:
        sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
        if sheet_id:
            leagues = get_sheets_data(sheets_service, sheet_id)
    except Exception as e:
        error = f"Ocurrió un error al cargar las ligas especiales: {e}"
        print(error)
    return jsonify(leagues)


@app.route("/api/lloros-awards/trofeos")
def api_lloros_trofeos():
    error = None
    trofeos = []
    try:
        sheet_id = config.TROFEOS_SHEETS.get(g.season)
        if sheet_id:
            trofeos = get_sheets_data(sheets_service, sheet_id)
    except Exception as e:
        error = f"Ocurrió un error al cargar los trofeos: {e}"
        print(error)
    return jsonify(trofeos)


# --- RUTAS FIJAS (NO DEPENDEN DE LA TEMPORADA) ---


@app.route("/palmares")
def palmares():
    """Displays historical records and awards."""
    seasons = defaultdict(lambda: defaultdict(list))
    error = None
    try:
        if not drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        file_metadata = find_file_on_drive(
            drive_service, config.PALMARES_FILENAME, config.GDRIVE_FOLDER_ID
        )
        if not file_metadata:
            raise FileNotFoundError(
                f"El archivo '{config.PALMARES_FILENAME}' no se encontró en Google Drive."
            )

        palmares_data = download_csv_as_dict(drive_service, file_metadata["id"])

        for row in palmares_data:
            season_data = row.get("temporada", "").strip()
            category = row.get("categoria", "").strip()
            value = row.get("valor", "").strip()

            if not season_data or not category:
                continue
            if category in ["multa", "sancion", "farolillo"]:
                seasons[season_data]["otros"].append({"tipo": category, "valor": value})
            else:
                seasons[season_data][category] = value
        sorted_seasons = sorted(seasons.items(), key=lambda item: item[0], reverse=True)
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al cargar el palmarés: {e}"
        print(error)
        sorted_seasons = []

    return render_template(
        "palmares.html",
        seasons=sorted_seasons,
        error=error,
        active_page="palmares",
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/reglamento")
def reglamento():
    """Displays the rules, fetching league data for context."""
    error = None
    leagues = []
    try:
        if sheets_service:
            sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
            if sheet_id:
                leagues = get_sheets_data(sheets_service, sheet_id)
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Sheets. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al cargar los datos para el índice: {e}"
        print(error)

    return render_template(
        "reglamento.html",
        leagues=leagues,
        error=error,
        active_page="reglamento",
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/admin", methods=["GET", "POST"])
def admin():
    """Admin panel for file status and management."""
    if "admin_logged_in" in session:
        file_statuses = []
        error = None
        try:
            if not drive_service:
                raise Exception("El servicio de Google Drive no está disponible.")

            comunicados_actual = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
            participacion_actual = (
                f"{config.PARTICIPACION_FILENAME_BASE}_{g.season}.csv"
            )

            filenames_to_check = [
                comunicados_actual,
                participacion_actual,
                config.PALMARES_FILENAME,
            ]
            dynamic_files = [comunicados_actual, participacion_actual]

            # Correctly call the imported function with all required arguments
            file_statuses = get_file_metadata(
                drive_service,
                config.GDRIVE_FOLDER_ID,
                filenames_to_check,
                dynamic_files,
            )

            sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
            if sheet_id:
                sheet_metadata = (
                    drive_service.files()
                    .get(fileId=sheet_id, fields="name, modifiedTime")
                    .execute()
                )
                dt_utc = parser.isoparse(sheet_metadata["modifiedTime"])
                dt_madrid = dt_utc.astimezone(pytz.timezone("Europe/Madrid"))
                formatted_date = dt_madrid.strftime("%d-%m-%Y a las %H:%M:%S")

                is_stale = (
                    datetime.now(pytz.timezone("Europe/Madrid")) - dt_madrid
                ) > timedelta(days=7)

                file_statuses.append(
                    {
                        "name": f"{sheet_metadata['name']} (Sheet)",
                        "status": "Encontrado",
                        "last_updated": formatted_date,
                        "is_stale": is_stale,
                    }
                )

        except ssl.SSLError as e:
            error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
            print(error)
        except Exception as e:
            error = f"No se pudo conectar con Google Drive para obtener el estado de los archivos: {e}"

        log_url = f"https://console.cloud.google.com/run/jobs/details/{config.CLOUD_RUN_REGION}/{config.CLOUD_RUN_JOB_NAME}/logs?project={config.GCP_PROJECT_ID}"

        return render_template(
            "admin_panel.html",
            active_page="admin",
            file_statuses=file_statuses,
            log_url=log_url,
            error=error,
            season=g.season,
            temporada_actual=config.TEMPORADA_ACTUAL,
            temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
        )

    if request.method == "POST":
        if request.form.get("password") == config.ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            flash("Contraseña incorrecta. Inténtalo de nuevo.", "error")

    return render_template(
        "admin_login.html",
        active_page="admin",
        season=g.season,
        temporada_actual=config.TEMPORADA_ACTUAL,
        temporadas_disponibles=config.TEMPORADAS_DISPONIBLES,
    )


@app.route("/logout")
def logout():
    """Logs out the admin user."""
    session.pop("admin_logged_in", None)
    flash("Has cerrado la sesión correctamente.", "info")
    return redirect(url_for("home"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
