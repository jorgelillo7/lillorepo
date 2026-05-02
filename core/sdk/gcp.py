import csv
import io
from datetime import datetime, timedelta

import pytz
from dateutil import parser
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from core.utils import get_logger

logger = get_logger(__name__)


# --- AUTHENTICATION ---

def get_google_service(api_name, api_version, service_account_file, scopes):
    """Returns an authenticated client using a Service Account."""
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=scopes
    )
    return build(api_name, api_version, credentials=credentials)


# --- GOOGLE DRIVE ---

def find_file_on_drive(service, name, folder_id):
    """Searches for a file by name in a Drive folder; returns its metadata or None."""
    query = f"name = '{name}' and '{folder_id}' in parents and trashed=false"
    response = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name, modifiedTime)")
        .execute()
    )
    return response.get("files", [])[0] if response.get("files") else None


def download_csv_from_drive(service, file_id) -> str:
    """Downloads a Drive file and returns its contents as a string."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue().decode("utf-8")


def download_csv_as_dict(service, file_id) -> list[dict]:
    """Downloads a CSV from Drive and returns it as a list of dicts."""
    if not file_id:
        raise FileNotFoundError("El ID del archivo CSV no fue proporcionado.")
    csv_content = download_csv_from_drive(service, file_id)
    return list(csv.DictReader(io.StringIO(csv_content)))


def upload_csv_to_drive(
    service, folder_id: str, filename: str, csv_content_string: str, existing_file_id
):
    """Uploads (or updates) a CSV string to a Drive folder."""
    media = MediaIoBaseUpload(
        io.BytesIO(csv_content_string.encode("utf-8")),
        mimetype="text/csv",
        resumable=True,
    )
    if existing_file_id:
        service.files().update(fileId=existing_file_id, media_body=media).execute()
        logger.info("Archivo actualizado en Drive.", extra={"file_name": filename})
    else:
        file_metadata = {"name": filename, "parents": [folder_id]}
        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        permission = {"type": "anyone", "role": "reader"}
        service.permissions().create(fileId=file.get("id"), body=permission).execute()
        logger.info(
            "Archivo creado y compartido públicamente en Drive.",
            extra={"file_name": filename},
        )


# --- GOOGLE SHEETS ---

def get_sheets_data(service, spreadsheet_id) -> list[dict]:
    """Reads and processes all sheets from a Google Spreadsheet."""
    sheet_metadata = (
        service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    )
    sheets = sheet_metadata.get("sheets", "")

    all_leagues_data = []
    for sheet in sheets:
        sheet_title = sheet.get("properties", {}).get("title", "Sin Título")
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=sheet_title)
            .execute()
        )
        values = result.get("values", [])

        if not values or len(values) < 6:
            continue

        league_info = {
            "nombre": values[0][1] if len(values[0]) > 1 else "N/A",
            "descripcion": values[1][1] if len(values[1]) > 1 else "N/A",
            "premio": values[2][1] if len(values[2]) > 1 else "N/A",
            "headers": values[4],
            "rows": values[5:],
        }
        all_leagues_data.append(league_info)
    return all_leagues_data


# --- FILE STATUS HELPERS ---

def get_file_metadata(service, folder_id: str, filenames: list, dynamic_files: list) -> list[dict]:
    """
    Returns metadata for a list of Drive files, including last-modified time
    and a staleness flag (True when a dynamic file has not been updated in 7+ days).
    """
    statuses = []
    now_madrid = datetime.now(pytz.timezone("Europe/Madrid"))

    for name in filenames:
        query = f"name = '{name}' and '{folder_id}' in parents and trashed=false"
        response = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name, modifiedTime)")
            .execute()
        )
        file = response.get("files", [])[0] if response.get("files") else None

        if file:
            dt_utc = parser.isoparse(file["modifiedTime"])
            dt_madrid = dt_utc.astimezone(pytz.timezone("Europe/Madrid"))
            formatted_date = dt_madrid.strftime("%d-%m-%Y a las %H:%M:%S")
            is_stale = name in dynamic_files and (now_madrid - dt_madrid) > timedelta(days=7)
            statuses.append(
                {
                    "name": name,
                    "status": "Encontrado",
                    "last_updated": formatted_date,
                    "is_stale": is_stale,
                }
            )
        else:
            statuses.append(
                {"name": name, "status": "No Encontrado", "last_updated": "N/A", "is_stale": False}
            )
    return statuses
