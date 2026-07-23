import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CRED_PATH = os.path.join(os.path.dirname(__file__), 'service_account.json')

def get_credentials():
    if not os.path.exists(CRED_PATH):
        raise FileNotFoundError(f"Archivo service_account.json no encontrado: {CRED_PATH}. Descarga las credenciales de cuenta de servicio desde Google Cloud Console")
    with open(CRED_PATH, 'r') as f:
        raw = f.read()
    print("DEBUG: Contenido service_account.json:", raw[:200] if raw else "(vacío)")
    creds = Credentials.from_service_account_file(CRED_PATH, scopes=SCOPES)
    return creds

def append_rows(sheet_id: str, values: list[list]):
    try:
        creds = get_credentials()
    except FileNotFoundError as e:
        raise Exception(f"Error de configuración: {e}")
    service = build('sheets', 'v4', credentials=creds)
    body = {'values': values}
    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range='A1',
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        print("DEBUG: Respuesta de Sheets:", result)
        return result
    except HttpError as e:
        print("DEBUG: HttpError capturado:", e)
        raise Exception(f"Error de API Google Sheets: {e}")
    except Exception as e:
        print("DEBUG: Excepción:", e)
        raise Exception(f"Error de conexión: {e}")