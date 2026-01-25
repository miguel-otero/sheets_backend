import io
import os
import re
import time
import tempfile
import logging
from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import google.auth
import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google_auth_httplib2 import AuthorizedHttp

from openpyxl import load_workbook

logger = logging.getLogger("sheets_automation")
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
DRIVE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

#Debug
SCOPES = [
  "https://www.googleapis.com/auth/drive",
  "https://www.googleapis.com/auth/spreadsheets",
]

# Ajusta si quieres. 60s suele funcionar bien para llamadas largas.
HTTP_TIMEOUT_SECONDS = int(os.getenv("GOOGLE_HTTP_TIMEOUT", "60"))


# ------------------------------------------------------------
# Models
# ------------------------------------------------------------
class ConvertXlsxRequest(BaseModel):
    xlsx_file_id: str = Field(..., description="Drive fileId o URL del XLSX")
    selected_tabs: List[str] = Field(..., min_items=1, description="Pestañas del XLSX a copiar (ej: ['mov_general'])")

    destination_folder_id: Optional[str] = Field(
        None, description="Drive folderId o URL destino. Si no se envía, usa la carpeta padre del XLSX."
    )
    new_spreadsheet_name: Optional[str] = Field(
        None, description="Nombre del Google Sheets destino. Si no se envía, usa '<xlsx_name> (seleccion)'."
    )

    value_input_option: Literal["RAW", "USER_ENTERED"] = Field(
        "RAW",
        description="RAW es más rápido/robusto. USER_ENTERED interpreta fórmulas/formatos tipo Sheets.",
    )

    # Control de chunking
    target_cells_per_request: int = Field(
        80000, ge=10000, le=200000, description="Aprox celdas por request a Sheets (ajusta si da error por tamaño)."
    )
    max_retries: int = Field(8, ge=1, le=15, description="Reintentos ante 429/5xx")


class ConvertXlsxResponse(BaseModel):
    spreadsheet_id: str
    spreadsheet_url: str
    name: str
    destination_folder_id: str


# ------------------------------------------------------------
# Helpers (Drive/Sheets)
# ------------------------------------------------------------
def extract_drive_id(s: str) -> str:
    """
    Extrae un ID de Drive desde un ID puro o desde una URL.
    """
    m = re.search(r"[-\w]{25,}", s or "")
    return m.group(0) if m else s


def build_google_services():
    """
    Construye clientes Drive/Sheets usando ADC (Cloud Run service account).
    Incluye timeout real (evita warning de per-request timeout).
    """
    creds, _ = google.auth.default(scopes=DRIVE_SHEETS_SCOPES)

    # httplib2 timeout a nivel de transporte
    http = httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS)
    authed_http = AuthorizedHttp(creds, http=http)

    drive_service = build("drive", "v3", http=authed_http, cache_discovery=False)
    sheets_service = build("sheets", "v4", http=authed_http, cache_discovery=False)

    return drive_service, sheets_service


def with_retries(fn, *, max_retries=8, base_sleep=1.0, retryable_status=(429, 500, 502, 503, 504)):
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in retryable_status and attempt < max_retries - 1:
                sleep = base_sleep * (2**attempt) + (0.1 * attempt)
                time.sleep(sleep)
                continue
            raise


def get_drive_file_metadata(drive_service, file_id: str, fields: str = "id,name,parents,mimeType,size"):
    return with_retries(
        lambda: drive_service.files()
        .get(fileId=file_id, fields=fields, supportsAllDrives=True)
        .execute()
    )


def ensure_folder_access(drive_service, folder_id_or_url: str, max_retries: int) -> str:
    folder_id = extract_drive_id(folder_id_or_url)
    meta = with_retries(
        lambda: drive_service.files()
        .get(fileId=folder_id, fields="id,name,mimeType", supportsAllDrives=True)
        .execute(),
        max_retries=max_retries,
    )
    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        raise ValueError(f"El destino no es una carpeta. name={meta.get('name')} mimeType={meta.get('mimeType')}")
    return folder_id


def download_drive_file(drive_service, file_id: str, out_path: str, *, max_retries: int, chunk_size: int = 8 * 1024 * 1024):
    """
    Descarga un archivo de Drive en chunks al filesystem (/tmp).
    """
    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.FileIO(out_path, "wb")
    downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)

    done = False
    while not done:
        status, done = with_retries(lambda: downloader.next_chunk(), max_retries=max_retries)
        if status:
            pct = int(status.progress() * 100)
            if pct % 10 == 0:
                logger.info("Descargando XLSX... %s%%", pct)

    fh.close()


def col_to_a1_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def a1_start(sheet_title: str, start_row: int, start_col: int = 1) -> str:
    return f"'{sheet_title}'!{col_to_a1_letter(start_col)}{start_row}"


def choose_chunk_rows(num_cols: int, target_cells_per_request: int, min_rows: int = 200, max_rows: int = 5000) -> int:
    if num_cols <= 0:
        return min_rows
    rows = target_cells_per_request // max(1, num_cols)
    return int(max(min_rows, min(max_rows, rows)))


def safe_cell(v):
    if v is None:
        return ""
    try:
        import datetime as dt
        if isinstance(v, (dt.datetime, dt.date)):
            return v.isoformat()
    except Exception:
        pass
    return v


def validate_sheet_title(title: str) -> str:
    """
    Sheets tiene restricciones en nombres. Excel casi siempre cumple, pero validamos por si acaso.
    """
    forbidden = set(r'[]:*?/\\')
    if any(ch in forbidden for ch in title):
        raise ValueError(f"Nombre de hoja inválido para Google Sheets: '{title}' (contiene caracteres prohibidos).")
    if len(title) > 100:
        raise ValueError(f"Nombre de hoja demasiado largo (>100): '{title}'")
    if title.strip() == "":
        raise ValueError("Nombre de hoja vacío no permitido.")
    return title


# ------------------------------------------------------------
# Core conversion
# ------------------------------------------------------------
def convert_xlsx_tabs_to_sheets(
    *,
    drive_service,
    sheets_service,
    xlsx_file_id: str,
    selected_tabs: List[str],
    destination_folder_id: Optional[str],
    new_spreadsheet_name: Optional[str],
    value_input_option: str,
    target_cells_per_request: int,
    max_retries: int,
) -> ConvertXlsxResponse:
    xlsx_file_id = extract_drive_id(xlsx_file_id)
    selected_tabs = [validate_sheet_title(t) for t in selected_tabs]

    # 1) Metadata XLSX (nombre + carpeta padre)
    meta = get_drive_file_metadata(drive_service, xlsx_file_id)
    xlsx_name = meta.get("name", "archivo.xlsx")
    parents = meta.get("parents") or []

    if destination_folder_id:
        destination_folder_id = ensure_folder_access(drive_service, destination_folder_id, max_retries=max_retries)
    else:
        if not parents:
            raise ValueError("No pude obtener la carpeta padre del XLSX; envía destination_folder_id.")
        destination_folder_id = parents[0]

    base_name = os.path.splitext(xlsx_name)[0]
    spreadsheet_name = new_spreadsheet_name or f"{base_name} (seleccion)"

    # 2) Descargar XLSX a /tmp
    tmp = tempfile.NamedTemporaryFile(prefix="xlsx_", suffix=".xlsx", dir="/tmp", delete=False)
    tmp_path = tmp.name
    tmp.close()

    logger.info("Descargando XLSX (fileId=%s) a %s", xlsx_file_id, tmp_path)
    try:
        download_drive_file(drive_service, xlsx_file_id, tmp_path, max_retries=max_retries)
        logger.info("Descarga completada: %s", tmp_path)

        # 3) Crear Google Sheets en carpeta destino (Drive API)
        created = with_retries(
            lambda: drive_service.files().create(
                body={
                    "name": spreadsheet_name,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [destination_folder_id],
                },
                fields="id,name",
                supportsAllDrives=True,
            ).execute(),
            max_retries=max_retries,
        )
        spreadsheet_id = created["id"]

        # 4) Leer XLSX streaming
        wb = load_workbook(filename=tmp_path, read_only=True, data_only=True)
        available = wb.sheetnames
        missing = [t for t in selected_tabs if t not in available]
        if missing:
            raise ValueError(f"Pestañas no encontradas: {missing}. Disponibles: {available}")

        # 5) Crear hojas seleccionadas
        add_requests = [{"addSheet": {"properties": {"title": t}}} for t in selected_tabs]
        with_retries(
            lambda: sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": add_requests}
            ).execute(),
            max_retries=max_retries,
        )

        # 6) Escribir cada hoja en chunks
        def flush_values(sheet_title: str, start_row: int, values_chunk):
            if not values_chunk:
                return
            rng = a1_start(sheet_title, start_row, 1)
            with_retries(
                lambda: sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=rng,
                    valueInputOption=value_input_option,
                    body={"values": values_chunk},
                ).execute(),
                max_retries=max_retries,
            )

        for tab in selected_tabs:
            ws = wb[tab]
            max_col = ws.max_column or 0
            chunk_rows = choose_chunk_rows(max_col, target_cells_per_request=target_cells_per_request)

            logger.info("Copiando hoja '%s' (cols≈%s) en chunks de %s filas", tab, max_col, chunk_rows)

            row_cursor = 1
            buffer = []

            for row in ws.iter_rows(values_only=True):
                buffer.append([safe_cell(v) for v in row])
                if len(buffer) >= chunk_rows:
                    flush_values(tab, row_cursor, buffer)
                    row_cursor += len(buffer)
                    buffer = []

            if buffer:
                flush_values(tab, row_cursor, buffer)

            logger.info("Hoja '%s' copiada", tab)

        # 7) Borrar Sheet1 si sobra
        meta_sheets = with_retries(
            lambda: sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))"
            ).execute(),
            max_retries=max_retries,
        )
        sheet1_ids = [
            s["properties"]["sheetId"]
            for s in meta_sheets.get("sheets", [])
            if s["properties"]["title"] == "Sheet1"
        ]
        if sheet1_ids and "Sheet1" not in selected_tabs:
            with_retries(
                lambda: sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [{"deleteSheet": {"sheetId": sheet1_ids[0]}}]},
                ).execute(),
                max_retries=max_retries,
            )

        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        return ConvertXlsxResponse(
            spreadsheet_id=spreadsheet_id,
            spreadsheet_url=url,
            name=spreadsheet_name,
            destination_folder_id=destination_folder_id,
        )

    finally:
        # Limpieza del temp XLSX
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            logger.warning("No pude borrar temp file: %s", tmp_path)


# Debug

def drive_client():
    creds, _ = google.auth.default(scopes=SCOPES)
    http = httplib2.Http(timeout=60)
    authed = AuthorizedHttp(creds, http=http)
    return build("drive", "v3", http=authed, cache_discovery=False)