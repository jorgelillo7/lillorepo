import csv
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
from core.sdk.biwenger import BiwengerClient
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
biwenger_client = None

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

players_map = {}

if config.BIWENGER_EMAIL and config.BIWENGER_PASSWORD:
    try:
        biwenger_client = BiwengerClient(
            config.BIWENGER_EMAIL,
            config.BIWENGER_PASSWORD,
            config.BIWENGER_LOGIN_URL,
            config.BIWENGER_ACCOUNT_URL,
            config.BIWENGER_LEAGUE_ID,
        )
        players_map = biwenger_client.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    except Exception as e:
        print(f"WARNING: No se pudo inicializar BiwengerClient o cargar jugadores: {e}")


# --- HELPERS ---

CLAUSULAZOS_CSV_FIELDS = ["fecha", "jugador", "equipo_vendedor", "equipo_comprador", "precio"]


def _parse_clausulazos(raw_data):
    """Transforma la respuesta cruda de la API en una lista de dicts normalizados.

    Estructura real (type=transfer, content items con type=clause):
    {
      "content": [
        {
          "type": "clause",
          "amount": 10158750,
          "from": {"name": "Ferraz fc"},          # equipo vendedor
          "to":   {"name": "Los caídos..."},       # equipo comprador
          "player": <id_int> | {"id":..,"name":..} # jugador
        }
      ],
      "date": 1776970759,
      "type": "transfer"
    }
    Un mismo entry puede contener varios clausulazos.
    """
    entries = raw_data.get("data", [])
    if isinstance(entries, dict):
        entries = list(entries.values())

    clausulazos = []
    madrid_tz = pytz.timezone("Europe/Madrid")

    for entry in entries:
        try:
            content = entry.get("content") or []
            clause_items = [c for c in content if c.get("type") == "clause"]
            if not clause_items:
                continue

            timestamp = entry.get("date", 0)
            fecha = datetime.fromtimestamp(timestamp, tz=madrid_tz).strftime("%d-%m-%Y %H:%M")

            for item in clause_items:
                player_data = item.get("player")
                if isinstance(player_data, dict):
                    jugador = player_data.get("name") or f"#{player_data.get('id', '?')}"
                elif player_data is not None:
                    player_id = int(player_data)
                    player_info = players_map.get(player_id, {})
                    jugador = player_info.get("name") or f"#{player_id}"
                else:
                    jugador = "Desconocido"

                from_team = item.get("from") or {}
                equipo_vendedor = from_team.get("name", "—")

                to_team = item.get("to") or {}
                equipo_comprador = to_team.get("name", "—")

                precio = int(item.get("amount", 0))

                clausulazos.append({
                    "fecha": fecha,
                    "jugador": jugador,
                    "equipo_vendedor": equipo_vendedor,
                    "equipo_comprador": equipo_comprador,
                    "precio": precio,
                })
        except Exception as parse_err:
            print(f"WARNING: Error parseando clausulazo: {parse_err} — entry: {entry}")

    return clausulazos


def _save_clausulazos_csv(clausulazos):
    """Guarda la lista de clausulazos en el CSV local."""
    try:
        with open(config.CLAUSULAZOS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CLAUSULAZOS_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(clausulazos)
        print(f"✅ CSV de clausulazos guardado en {config.CLAUSULAZOS_CSV_PATH} ({len(clausulazos)} entradas).")
    except Exception as e:
        print(f"WARNING: No se pudo guardar el CSV de clausulazos: {e}")


def _build_tabla_justicia(clausulazos):
    """Construye el resumen de ataques realizados y recibidos por cada equipo.

    Devuelve una lista con todos los equipos, ordenada por ataques realizados:
    [
      {
        'equipo': 'Rayo Entrebirras',
        'total_hechos': 4,
        'total_recibidos': 3,
        'punto_de_mira': 'Ferraz fc',       # a quien más han atacado
        'mayor_agresor': 'Kairat FC',       # quien más les ha atacado a ellos
        'hechos': [('Ferraz fc', 3), ...],
        'recibidos': [('Kairat FC', 2), ...],
      },
      ...
    ]
    """
    from collections import defaultdict
    ataques_hechos = defaultdict(lambda: defaultdict(int))
    ataques_recibidos = defaultdict(lambda: defaultdict(int))
    equipos = set()

    for c in clausulazos:
        comprador = c["equipo_comprador"]
        vendedor = c["equipo_vendedor"]
        if comprador and comprador != "—" and vendedor and vendedor != "—":
            ataques_hechos[comprador][vendedor] += 1
            ataques_recibidos[vendedor][comprador] += 1
            equipos.add(comprador)
            equipos.add(vendedor)

    tabla = []
    for equipo in equipos:
        hechos = dict(ataques_hechos.get(equipo, {}))
        recibidos = dict(ataques_recibidos.get(equipo, {}))
        hechos_sorted = sorted(hechos.items(), key=lambda x: x[1], reverse=True)
        recibidos_sorted = sorted(recibidos.items(), key=lambda x: x[1], reverse=True)
        tabla.append({
            "equipo": equipo,
            "total_hechos": sum(hechos.values()),
            "total_recibidos": sum(recibidos.values()),
            "punto_de_mira": hechos_sorted[0][0] if hechos_sorted else "—",
            "mayor_agresor": recibidos_sorted[0][0] if recibidos_sorted else "—",
            "hechos": hechos_sorted,
            "recibidos": recibidos_sorted,
        })

    tabla.sort(key=lambda x: x["total_hechos"], reverse=True)
    return tabla


def fetch_clausulazos():
    """Llama a la API de Biwenger, guarda en CSV y devuelve la lista."""
    if not biwenger_client:
        return [], [], "El cliente de Biwenger no está disponible (faltan credenciales)."
    try:
        raw = biwenger_client.get_clausulazos(config.CLAUSULAZOS_URL)
        clausulazos = _parse_clausulazos(raw)
        _save_clausulazos_csv(clausulazos)
        tabla_justicia = _build_tabla_justicia(clausulazos)
        return clausulazos, tabla_justicia, None
    except Exception as e:
        print(f"ERROR obteniendo clausulazos: {e}")
        return [], [], f"Error al obtener clausulazos de Biwenger: {e}"


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
    cronicas = []
    clausulazos = []
    clausulazos_error = None

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
        cronicas = [
            m for m in all_messages if m.get("categoria", "").strip() == "cronica"
        ]
    except ssl.SSLError as e:
        error = f"Error de SSL al conectar con Google Drive. Puede ser un problema con tu red o certificados locales. ({e})"
        print(error)
    except Exception as e:
        error = f"Ocurrió un error al cargar los datos de la temporada {g.season}: {e}"
        print(error)

    clausulazos, tabla_justicia, clausulazos_error = fetch_clausulazos()

    return render_template(
        "salseo.html",
        datos=datos_curiosos,
        cronicas=cronicas,
        clausulazos=clausulazos,
        tabla_justicia=tabla_justicia,
        clausulazos_error=clausulazos_error,
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


@app.route("/api/debug/clausulazos")
@app.route("/api/debug/clausulazos/<event_type>")
def api_debug_clausulazos(event_type="clauseIncrement"):
    """Endpoint temporal para inspeccionar el JSON crudo de la API con distintos tipos.
    Prueba: /api/debug/clausulazos/clause  o  /api/debug/clausulazos/transfer
    """
    if not biwenger_client:
        return jsonify({"error": "BiwengerClient no disponible"}), 503
    try:
        base = f"{config.BIWENGER_BASE_URL}/league/{config.BIWENGER_LEAGUE_ID}/board"
        url = f"{base}?type={event_type}&limit=20&fields=*,content(*,player(*),user(*))"
        raw = biwenger_client.get_clausulazos(url)
        return jsonify(raw)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
