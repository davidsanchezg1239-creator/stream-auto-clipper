import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

STATE_FILE = Path("credentials/tiktok_storage.json")

async def test():
    print("Probando apertura de Chrome estándar para TikTok...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
        print("¡Ventana de TikTok abierta exitosamente en tu pantalla!", flush=True)
        print("Esperando a que inicies sesión en la ventana...", flush=True)
        
        while not page.is_closed():
            cookies = await context.cookies()
            logged_in = any(c['name'] in ['sessionid', 'sessionid_ss', 'sid_tt'] for c in cookies)
            if logged_in:
                print("¡Inicio de sesión en TikTok confirmado!", flush=True)
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(STATE_FILE))
                print(f"Estado de sesión guardado en {STATE_FILE}", flush=True)
                await asyncio.sleep(3)
                break
            await asyncio.sleep(2)
            
        try:
            await browser.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(test())
