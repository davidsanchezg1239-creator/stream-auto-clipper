import asyncio
import sys
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

async def test():
    async with async_playwright() as p:
        print("Intentando abrir navegador Chrome...", flush=True)
        try:
            browser = await p.chromium.launch(channel="chrome", headless=False)
            print("Navegador Chrome abierto con éxito!", flush=True)
        except Exception as e:
            print(f"No se pudo con canal chrome ({e}), intentando con chromium...", flush=True)
            browser = await p.chromium.launch(headless=False)
            print("Chromium abierto con éxito!", flush=True)

        page = await browser.new_page()
        await page.goto("https://www.tiktok.com/login")
        print("Página de login cargada!", flush=True)
        await asyncio.sleep(6)
        await browser.close()
        print("Prueba completada.", flush=True)

if __name__ == "__main__":
    asyncio.run(test())
