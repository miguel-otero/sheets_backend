"""
This is the main entry point of the application. It initializes the FastAPI
interface and launches it.
"""
# External Dependencies
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from googleapiclient.errors import HttpError
from fastapi import HTTPException


# Inner dependencies
from config import DEPLOYMENT_VERSION, xlsx_file_id, destination_folder_id
from gs import build_google_services, drive_client, ConvertXlsxToExistingSheetsRequest, write_xlsx_tabs_into_existing_spreadsheet, logger


app = FastAPI()


# Add CORS middleware to allow cross-origin requests.
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


@app.get("/")
def root():
  """Root endpoint to verify the API is running."""
  return {
    "message": "Welcome to Sheets Automations Clinica Versalles API",
    "version": DEPLOYMENT_VERSION,
  }

@app.post("/convert/xlsx-to-existing-sheets")
def convert_into_existing(payload: ConvertXlsxToExistingSheetsRequest):
    drive_service, sheets_service = build_google_services()

    try:
        return write_xlsx_tabs_into_existing_spreadsheet(
            drive_service=drive_service,
            sheets_service=sheets_service,
            xlsx_file_id=payload.xlsx_file_id,
            target_spreadsheet_id=payload.target_spreadsheet_id,
            selected_tabs=payload.selected_tabs,
            wipe_mode=payload.wipe_mode,
            value_input_option=payload.value_input_option,
            target_cells_per_request=payload.target_cells_per_request,
            max_retries=payload.max_retries,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HttpError as e:
        status = getattr(e.resp, "status", None)
        content = getattr(e, "content", b"")
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Error llamando a Google APIs (Drive/Sheets).",
                "http_status": status,
                "error": str(e),
                "content": content.decode("utf-8", errors="ignore") if isinstance(content, (bytes, bytearray)) else str(content),
            },
        )
    except Exception as e:
        logger.exception("Fallo inesperado")
        raise HTTPException(status_code=500, detail=str(e))

# Debug

@app.get("/debug/whoami")
def whoami():
    drive = drive_client()
    about = drive.about().get(fields="user(emailAddress,permissionId),storageQuota").execute()
    return about

