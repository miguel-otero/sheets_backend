from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

import io
import os
import time
from typing import List, Optional


def with_retries(fn, *, max_retries=8, base_sleep=1.0, retryable_status=(429, 500, 502, 503, 504)):
    for attempt in range(max_retries):
        try:
            return fn()
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in retryable_status and attempt < max_retries - 1:
                sleep = base_sleep * (2 ** attempt) + (0.1 * attempt)
                time.sleep(sleep)
                continue
            raise

def get_drive_file_metadata(file_id: str, fields: str = "id,name,parents,mimeType,size"):
    return with_retries(lambda: drive_service.files().get(
        fileId=file_id,
        fields=fields,
        supportsAllDrives=True
    ).execute())

def download_drive_file(file_id: str, out_path: str, chunk_size: int = 1024 * 1024 * 8):
    """
    Descarga un archivo de Drive a disco en chunks (por defecto 8MB).
    """
    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.FileIO(out_path, "wb")
    downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)

    done = False
    last_pct = -1
    while not done:
        status, done = with_retries(lambda: downloader.next_chunk())
        if status:
            pct = int(status.progress() * 100)
            if pct != last_pct and pct % 5 == 0:
                print(f"Descargando XLSX... {pct}%")
                last_pct = pct
    fh.close()

def col_to_a1_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def a1_start(sheet_title: str, start_row: int, start_col: int = 1) -> str:
    return f"'{sheet_title}'!{col_to_a1_letter(start_col)}{start_row}"

def choose_chunk_rows(num_cols: int, target_cells_per_request: int = 80_000, min_rows: int = 200, max_rows: int = 5000) -> int:
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

def xlsx_drive_to_google_sheets(
    *,
    xlsx_file_id: str,
    selected_tabs: List[str],
    destination_folder_id: Optional[str] = None,
    new_spreadsheet_name: Optional[str] = None,
    value_input_option: str = "RAW",          # "RAW" es más rápido/robusto. Usa "USER_ENTERED" si necesitas fórmulas interpretadas.
    target_cells_per_request: int = 80_000,   # baja a 50_000 si tienes errores por tamaño de request
) -> str:
    """
    Convierte SOLO las pestañas seleccionadas de un XLSX en Drive (por fileId)
    a un Google Sheets nuevo en la carpeta destino.

    - Si destination_folder_id es None, usa la carpeta padre del XLSX.
    - Retorna spreadsheetId del Google Sheets creado.
    """
    # 1) Metadata para nombre y carpeta padre (si no pasas folderId)
    meta = get_drive_file_metadata(xlsx_file_id)
    xlsx_name = meta.get("name", "archivo.xlsx")
    parents = meta.get("parents") or []

    if destination_folder_id is None:
        if not parents:
            raise ValueError("El archivo no tiene carpeta padre accesible; pasa destination_folder_id explícitamente.")
        destination_folder_id = parents[0]

    base_name = os.path.splitext(xlsx_name)[0]
    spreadsheet_name = new_spreadsheet_name or f"{base_name} (seleccion)"

    # 2) Descargar XLSX a disco local (robusto para archivos grandes)
    local_xlsx = "/content/input.xlsx"
    if os.path.exists(local_xlsx):
        os.remove(local_xlsx)

    print("Iniciando descarga del XLSX desde Drive...")
    download_drive_file(xlsx_file_id, local_xlsx)
    print("Descarga completada:", local_xlsx)

    # 3) Crear Google Sheets en la carpeta destino
    file_metadata = {
        "name": spreadsheet_name,
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [destination_folder_id],
    }
    created = with_retries(lambda: drive_service.files().create(
        body=file_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute())
    spreadsheet_id = created["id"]
    print("Google Sheets creado:", spreadsheet_id)

    # 4) Cargar XLSX en modo streaming
    from openpyxl import load_workbook
    wb = load_workbook(filename=local_xlsx, read_only=True, data_only=True)

    available = wb.sheetnames
    missing = [t for t in selected_tabs if t not in available]
    if missing:
        raise ValueError(f"Pestañas no encontradas: {missing}. Disponibles: {available}")

    # 5) Crear hojas (tabs) en el nuevo spreadsheet
    add_requests = [{"addSheet": {"properties": {"title": t}}} for t in selected_tabs]
    with_retries(lambda: sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": add_requests}
    ).execute())

    # 6) Copiar datos por chunks
    def flush_values(sheet_title: str, start_row: int, values_chunk):
        if not values_chunk:
            return
        rng = a1_start(sheet_title, start_row, 1)
        body = {"values": values_chunk}
        with_retries(lambda: sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=rng,
            valueInputOption=value_input_option,
            body=body
        ).execute())

    for tab in selected_tabs:
        ws = wb[tab]
        max_col = ws.max_column or 0
        chunk_rows = choose_chunk_rows(max_col, target_cells_per_request=target_cells_per_request)

        print(f"\n➡️ Copiando '{tab}' (cols≈{max_col}) en chunks de {chunk_rows} filas...")

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

        print(f"✅ '{tab}' copiada.")

    # 7) Borrar "Sheet1" si existe
    meta_sheets = with_retries(lambda: sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))"
    ).execute())
    sheet1_ids = [
        s["properties"]["sheetId"]
        for s in meta_sheets.get("sheets", [])
        if s["properties"]["title"] == "Sheet1"
    ]
    if sheet1_ids and "Sheet1" not in selected_tabs:
        with_retries(lambda: sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"deleteSheet": {"sheetId": sheet1_ids[0]}}]}
        ).execute())

    print("\n🎉 Listo. Link:")
    print("https://docs.google.com/spreadsheets/d/" + spreadsheet_id)
    return spreadsheet_id
