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
from gs import ConvertXlsxResponse, ConvertXlsxRequest, build_google_services, convert_xlsx_tabs_to_sheets, drive_client


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

@app.post("/convert_gs", response_model=ConvertXlsxResponse)
def convert_gs(payload: ConvertXlsxRequest):
    drive_service, sheets_service = build_google_services()

    try:
        return convert_xlsx_tabs_to_sheets(
            drive_service=drive_service,
            sheets_service=sheets_service,
            xlsx_file_id=payload.xlsx_file_id,
            selected_tabs=payload.selected_tabs,
            destination_folder_id=payload.destination_folder_id,
            new_spreadsheet_name=payload.new_spreadsheet_name,
            value_input_option=payload.value_input_option,
            target_cells_per_request=payload.target_cells_per_request,
            max_retries=payload.max_retries,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HttpError as e:
        # Drive suele devolver 404 también cuando no hay permisos
        status = getattr(e.resp, "status", None)
        detail = getattr(e, "content", None)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Error llamando a Google APIs (Drive/Sheets). Revisa permisos de la service account sobre el archivo/carpeta.",
                "http_status": status,
                "error": str(e),
                "content": detail.decode("utf-8", errors="ignore") if isinstance(detail, (bytes, bytearray)) else str(detail),
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

