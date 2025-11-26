import csv
import hashlib
import io
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

from packages.biwenger_tools.scraper_job import config
from packages.biwenger_tools.scraper_job.logic.processing import (
    categorize_title,
    process_participation,
    sort_messages,
    get_all_board_messages,
)
from core.sdk.gcp import (
    get_google_service,
    find_file_on_drive,
    download_csv_as_dict,
    upload_csv_to_drive,
)
from core.sdk.biwenger import BiwengerClient
from core.utils import read_secret_from_file


def main():
    """
    Función principal que orquesta el scraping de mensajes, el procesamiento
    y la subida de datos a Google Drive.
    """
    try:
        print(f"--- Iniciando scraper para la temporada: {config.TEMPORADA_ACTUAL} ---")

        # --- 1. Leer secretos y configurar clientes/servicios ---
        biwenger_email = (
            read_secret_from_file(config.BIWENGER_EMAIL_PATH) or config.BIWENGER_EMAIL
        )
        biwenger_password = (
            read_secret_from_file(config.BIWENGER_PASSWORD_PATH)
            or config.BIWENGER_PASSWORD
        )
        gdrive_folder_id = (
            read_secret_from_file(config.GDRIVE_FOLDER_ID_PATH)
            or config.GDRIVE_FOLDER_ID
        )

        if not all([biwenger_email, biwenger_password, gdrive_folder_id]):
            raise ValueError(
                "¡Error! No se pudieron leer todas las credenciales necesarias."
            )

        # Construct paths relative to the current file
        base_dir = os.path.dirname(__file__)
        service_account_path = os.path.join(base_dir, "biwenger-tools-sa.json")
        if os.path.exists(config.SERVICE_ACCOUNT_PATH):
            service_account_path = config.SERVICE_ACCOUNT_PATH

        drive_service = get_google_service(
            "drive", "v3", service_account_path, config.SCOPES
        )
        biwenger = BiwengerClient(
            biwenger_email,
            biwenger_password,
            config.LOGIN_URL,
            config.ACCOUNT_URL,
            config.LEAGUE_ID,
        )

        # --- 2. Descargar datos existentes de Google Drive ---
        comunicados_filename = f"comunicados_{config.TEMPORADA_ACTUAL}.csv"
        comunicados_file_meta = find_file_on_drive(
            drive_service, comunicados_filename, gdrive_folder_id
        )

        all_messages = []
        existing_ids = set()
        if comunicados_file_meta:
            all_messages = download_csv_as_dict(
                drive_service, comunicados_file_meta["id"]
            )
            existing_ids = {msg["id_hash"] for msg in all_messages}
        else:
            print(f"ℹ️  No se encontró '{comunicados_filename}'. Se creará uno nuevo.")

        board_messages = get_all_board_messages(
            biwenger, f"{config.BASE_URL}/league/{config.LEAGUE_ID}/board?type=text"
        )

        print(f"📊 Total de mensajes descargados: {len(board_messages)}")
        user_map = biwenger.get_league_users(config.LEAGUE_USERS_URL)

        # --- 4. Procesar y fusionar datos ---
        new_messages_count = 0
        for item in board_messages:
            content_html = item.get("content", "")
            soup = BeautifulSoup(content_html, "html.parser")
            content_text = soup.get_text(separator=" ", strip=True)
            unique_string = f"{item.get('date', '')}{content_text}"
            id_hash = hashlib.sha256(unique_string.encode("utf-8")).hexdigest()

            if id_hash not in existing_ids:
                new_messages_count += 1
                author = item.get("author")
                author_id = author.get("id") if author else None
                author_name = user_map.get(author_id, "Autor Desconocido")

                # ✅ Conversión robusta a zona horaria Madrid
                fecha_utc = datetime.fromtimestamp(item["date"], tz=timezone.utc)
                fecha_madrid = fecha_utc.astimezone(ZoneInfo("Europe/Madrid"))
                fecha_str = fecha_madrid.strftime("%d-%m-%Y %H:%M:%S")

                all_messages.append(
                    {
                        "id_hash": id_hash,
                        "fecha": fecha_str,
                        "autor": author_name,
                        "titulo": item.get("title", "Sin título"),
                        "contenido": content_html,
                        "categoria": categorize_title(item.get("title", "")),
                    }
                )

        # --- 5. Si hay cambios, subir los archivos actualizados a Drive ---
        if new_messages_count > 0:
            print(f"\n✅ Se han encontrado {new_messages_count} mensajes nuevos.")
            all_messages = sort_messages(all_messages)

            # Subir archivo de comunicados
            output_comunicados = io.StringIO()
            writer = csv.DictWriter(
                output_comunicados,
                fieldnames=[
                    "id_hash",
                    "fecha",
                    "autor",
                    "titulo",
                    "contenido",
                    "categoria",
                ],
            )
            writer.writeheader()
            writer.writerows(all_messages)
            existing_comunicados_id = (
                comunicados_file_meta["id"] if comunicados_file_meta else None
            )
            upload_csv_to_drive(
                drive_service,
                gdrive_folder_id,
                comunicados_filename,
                output_comunicados.getvalue(),
                existing_comunicados_id,
            )

            # Subir archivo de participación
            participacion_filename = f"participacion_{config.TEMPORADA_ACTUAL}.csv"
            participation_data = process_participation(all_messages, user_map)
            participation_file_meta = find_file_on_drive(
                drive_service, participacion_filename, gdrive_folder_id
            )
            output_part = io.StringIO()
            writer = csv.DictWriter(
                output_part,
                fieldnames=["autor", "comunicados", "datos", "cesiones", "cronicas"],
            )
            writer.writeheader()
            writer.writerows(participation_data)
            existing_participation_id = (
                participation_file_meta["id"] if participation_file_meta else None
            )
            upload_csv_to_drive(
                drive_service,
                gdrive_folder_id,
                participacion_filename,
                output_part.getvalue(),
                existing_participation_id,
            )
        else:
            print("\n✅ No hay mensajes nuevos.")

    except Exception as e:
        print(f"❌ Ocurrió un error inesperado: {e}")


if __name__ == "__main__":
    main()
