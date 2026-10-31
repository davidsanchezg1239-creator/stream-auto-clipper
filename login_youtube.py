import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]
SECRETS_FILE = Path("credentials/client_secret.json")
TOKEN_FILE = Path("credentials/youtube_token.json")

def main():
    if not SECRETS_FILE.exists():
        print(f"Error: {SECRETS_FILE} not found!", flush=True)
        return

    print("Iniciando proceso de autorización de YouTube...", flush=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
    
    # Run local server on an available port, prompting for offline access (refresh token)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        success_message="¡Autorización completada! Ya puedes cerrar esta pestaña y volver a la consola."
    )
    
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as token:
        token.write(creds.to_json())
    
    print(f"¡Autorización exitosa! Token guardado en: {TOKEN_FILE}", flush=True)
    
    try:
        service = build("youtube", "v3", credentials=creds)
        channels_res = service.channels().list(mine=True, part="snippet").execute()
        items = channels_res.get("items", [])
        if items:
            title = items[0]["snippet"]["title"]
            print(f"Conectado exitosamente al canal de YouTube: {title}", flush=True)
        else:
            print("Conectado a la cuenta de Google con éxito.", flush=True)
    except Exception as e:
        print(f"Nota: {e}", flush=True)

if __name__ == "__main__":
    main()
