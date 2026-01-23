"""
This is the main entry point of the application. It initializes the FastAPI
interface and launches it.
"""
# External Dependencies
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Inner dependencies
from config import DEPLOYMENT_VERSION, xlsx_file_id, destination_folder_id
from gs import xlsx_drive_to_google_sheets


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

@app.post("/convert_gs")
def convert_gs():
  spreadsheet_id = xlsx_drive_to_google_sheets(
    xlsx_file_id=xlsx_file_id,
    destination_folder_id=destination_folder_id,
    selected_tabs=["mov_general"],      # aquí eliges las pestañas
    new_spreadsheet_name="prueba",
    value_input_option="RAW",           # más robusto/rápido
    target_cells_per_request=80_000
  )
