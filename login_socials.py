import sys
import asyncio
from app.publishers.browser_uploader import browser_uploader

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

async def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ["tiktok", "instagram"]:
        print("Uso: python login_socials.py [tiktok|instagram]", flush=True)
        return

    platform = sys.argv[1]
    print(f"Abriendo navegador Chromium para iniciar sesión en {platform.upper()}...", flush=True)
    print("Inicia sesión normalmente en la ventana que se acaba de abrir.", flush=True)
    print("Cuando termines de iniciar sesión y veas tu perfil o inicio, el navegador guardará tu sesión automáticamente.", flush=True)

    res = await browser_uploader.launch_login_session(platform)
    print(f"¡Sesión de {platform.upper()} guardada con éxito!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
