import os

DEPLOYMENT_VERSION = os.environ.get("DEPLOYMENT_VERSION", "local")

xlsx_file_id = os.environ.get("xlsx_file_id")
destination_folder_id = os.environ.get("destination_folder_id")
