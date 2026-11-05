import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import settings, BASE_DIR

logger = logging.getLogger("browser_uploader")

CREDENTIALS_DIR = BASE_DIR / "credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

class BrowserUploader:
    def __init__(self):
        self.tiktok_storage = CREDENTIALS_DIR / "tiktok_storage.json"
        self.instagram_storage = CREDENTIALS_DIR / "instagram_storage.json"

    def is_logged_in(self, platform: str) -> bool:
        """Checks if a saved cookies storage file exists for the platform."""
        target = self.tiktok_storage if platform == "tiktok" else self.instagram_storage
        return target.exists() and target.stat().st_size > 10

    def set_session_cookie(self, platform: str, session_id: str, extra_user_id: Optional[str] = None):
        """Allows direct injection of sessionid cookie copied from browser."""
        import json
        clean_sid = session_id.strip()
        if platform == "tiktok":
            cookies = [
                {
                    "name": "sessionid",
                    "value": clean_sid,
                    "domain": ".tiktok.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                },
                {
                    "name": "sessionid_ss",
                    "value": clean_sid,
                    "domain": ".tiktok.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                },
                {
                    "name": "sid_tt",
                    "value": clean_sid,
                    "domain": ".tiktok.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                }
            ]
            self.tiktok_storage.write_text(json.dumps({"cookies": cookies, "origins": []}, indent=2), encoding="utf-8")
            logger.info("TikTok session cookies saved successfully via direct sessionid.")
        elif platform == "instagram":
            cookies = [
                {
                    "name": "sessionid",
                    "value": clean_sid,
                    "domain": ".instagram.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                }
            ]
            if extra_user_id:
                cookies.append({
                    "name": "ds_user_id",
                    "value": extra_user_id.strip(),
                    "domain": ".instagram.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "None"
                })
            self.instagram_storage.write_text(json.dumps({"cookies": cookies, "origins": []}, indent=2), encoding="utf-8")
            logger.info("Instagram session cookies saved successfully via direct sessionid.")

    async def launch_login_session(self, platform: str):
        """
        Launches an interactive, visible Chrome window.
        Allows the user to log in manually, complete 2FA or captchas,
        and saves the session cookies into storage_state JSON.
        """
        from playwright.async_api import async_playwright

        target_file = self.tiktok_storage if platform == "tiktok" else self.instagram_storage
        target_url = "https://www.tiktok.com/login" if platform == "tiktok" else "https://www.instagram.com/accounts/login/"

        logger.info(f"Opening Chrome for interactive {platform} login...")
        print(f"\n=======================================================", flush=True)
        print(f"Abriendo ventana de Chrome para {platform.upper()}...", flush=True)
        print(f"Por favor revisa tu barra de tareas o pantalla.", flush=True)
        print(f"=======================================================\n", flush=True)

        async with async_playwright() as p:
            # Launch real Chrome in headed mode
            try:
                browser = await p.chromium.launch(channel="chrome", headless=False)
            except Exception:
                browser = await p.chromium.launch(headless=False)

            context = await browser.new_context(
                viewport={"width": 1280, "height": 850},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded")

            print(f"¡Ventana de {platform.upper()} abierta! Inicia sesión en tu cuenta...", flush=True)

            # Polling loop until user logs in or closes window
            try:
                for _ in range(600):  # Wait up to 10 minutes
                    if page.is_closed():
                        break

                    cookies = await context.cookies()
                    logged = False
                    if platform == "tiktok":
                        logged = any(c['name'] in ['sessionid', 'sessionid_ss', 'sid_tt', 'passport_csrf_token'] for c in cookies)
                    elif platform == "instagram":
                        logged = any(c['name'] in ['sessionid', 'ds_user_id'] for c in cookies)

                    if logged:
                        print(f"¡Inicio de sesión en {platform.upper()} detectado exitosamente!", flush=True)
                        await context.storage_state(path=str(target_file))
                        print(f"Sesión guardada permanentemente en: {target_file}", flush=True)
                        await asyncio.sleep(3)
                        break

                    await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"Interaction exception: {e}")
            finally:
                # Save on exit if cookies exist
                try:
                    cookies = await context.cookies()
                    if any(c['name'] in ['sessionid', 'sessionid_ss', 'sid_tt', 'ds_user_id'] for c in cookies):
                        await context.storage_state(path=str(target_file))
                except Exception:
                    pass

                try:
                    await browser.close()
                except Exception:
                    pass

            return {"success": self.is_logged_in(platform), "platform": platform}

    async def upload_tiktok_reel(self, video_path: str, caption: str) -> Dict[str, Any]:
        """Automates uploading a vertical short to TikTok using saved storage state."""
        from playwright.async_api import async_playwright

        target_file = Path(video_path)
        if not target_file.is_absolute():
            target_file = BASE_DIR / target_file

        if not target_file.exists():
            return {"success": False, "error": f"Video not found: {target_file}"}

        if not self.tiktok_storage.exists():
            return {"success": False, "error": "TikTok not authenticated. Run login first."}

        logger.info(f"Starting automated TikTok upload for {target_file.name}...")

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(channel="chrome", headless=True)
                except Exception:
                    browser = await p.chromium.launch(headless=True)

                context = await browser.new_context(storage_state=str(self.tiktok_storage))
                page = await context.new_page()
                await page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="domcontentloaded")

                if "login" in page.url:
                    await browser.close()
                    return {"success": False, "error": "TikTok session expired. Please re-login."}

                # Locate file input (attached, even if hidden behind drag-and-drop UI)
                upload_input = page.locator('input[type="file"]').first
                await upload_input.wait_for(state="attached", timeout=30000)
                await upload_input.set_input_files(str(target_file))
                logger.info("Video file attached to TikTok.")

                await asyncio.sleep(5)
                # Fill caption
                caption_div = page.locator('div[contenteditable="true"]').first
                if await caption_div.count() > 0:
                    await caption_div.fill(caption[:150])

                await asyncio.sleep(6)
                # Click publish
                publish_btn = page.locator('button:has-text("Publicar"), button:has-text("Post")').first
                if await publish_btn.count() > 0:
                    await publish_btn.click(force=True, timeout=15000)
                    await asyncio.sleep(8)
                    logger.info("TikTok publish clicked!")

                await browser.close()
                return {"success": True, "platform": "tiktok", "message": "Uploaded successfully to TikTok"}
        except Exception as e:
            logger.error(f"Error in TikTok browser upload: {e}")
            return {"success": False, "error": str(e)}

    async def upload_instagram_reel(self, video_path: str, caption: str) -> Dict[str, Any]:
        """Automates uploading an Instagram Reel using saved storage state."""
        from playwright.async_api import async_playwright

        target_file = Path(video_path)
        if not target_file.is_absolute():
            target_file = BASE_DIR / target_file

        if not target_file.exists():
            return {"success": False, "error": f"Video not found: {target_file}"}

        if not self.instagram_storage.exists():
            return {"success": False, "error": "Instagram not authenticated. Run login first."}

        logger.info(f"Starting automated Instagram Reel upload for {target_file.name}...")

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(channel="chrome", headless=True)
                except Exception:
                    browser = await p.chromium.launch(headless=True)

                context = await browser.new_context(storage_state=str(self.instagram_storage))
                page = await context.new_page()
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")

                if "accounts/login" in page.url:
                    await browser.close()
                    return {"success": False, "error": "Instagram session expired. Please re-login."}

                await asyncio.sleep(3)
                # Dismiss modal overlays like "Ahora no"
                for dismiss in ["Ahora no", "Not Now", "Cancelar", "Cancel"]:
                    try:
                        btn = page.locator(f'button:has-text("{dismiss}")')
                        if await btn.count() > 0:
                            await btn.first.click(force=True, timeout=3000)
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                # Click Create button
                create_locator = page.locator('svg[aria-label="Nueva publicación"], svg[aria-label="Crear"], span:has-text("Crear"), a[href*="create"]').first
                await create_locator.wait_for(state="attached", timeout=20000)
                await create_locator.click(force=True)

                # Upload file on hidden file input
                file_input = page.locator('input[type="file"]').first
                await file_input.wait_for(state="attached", timeout=20000)
                await file_input.set_input_files(str(target_file))

                # Step through modals: Siguiente -> Siguiente -> Caption -> Compartir
                await asyncio.sleep(4)
                next_btn = page.locator('[role="dialog"]').locator('div[role="button"]:has-text("Siguiente"), button:has-text("Siguiente"), div[role="button"]:has-text("Next"), button:has-text("Next")').last
                if await next_btn.count() > 0:
                    try:
                        await next_btn.click(force=True, timeout=5000)
                    except Exception:
                        await next_btn.evaluate("el => el.click()")
                    await asyncio.sleep(3)

                next_btn2 = page.locator('[role="dialog"]').locator('div[role="button"]:has-text("Siguiente"), button:has-text("Siguiente"), div[role="button"]:has-text("Next"), button:has-text("Next")').last
                if await next_btn2.count() > 0:
                    try:
                        await next_btn2.click(force=True, timeout=5000)
                    except Exception:
                        await next_btn2.evaluate("el => el.click()")
                    await asyncio.sleep(3)

                caption_area = page.locator('div[aria-label="Escribe un pie de foto..."], div[role="textbox"], textarea').first
                if await caption_area.count() > 0:
                    try:
                        await caption_area.fill(caption[:300])
                    except Exception:
                        await caption_area.click(force=True)
                        await page.keyboard.type(caption[:300])

                await asyncio.sleep(2)
                # Specific button inside dialog header to avoid root mount div
                share_btn = page.locator('[role="dialog"]').locator('div[role="button"]:has-text("Compartir"), button:has-text("Compartir"), div[role="button"]:has-text("Share"), button:has-text("Share")').last
                if await share_btn.count() == 0:
                    share_btn = page.locator('div[role="button"]:has-text("Compartir"), button:has-text("Compartir"), div[role="button"]:has-text("Share"), button:has-text("Share")').last

                if await share_btn.count() > 0:
                    try:
                        await share_btn.scroll_into_view_if_needed(timeout=3000)
                        await share_btn.click(force=True, timeout=10000)
                    except Exception:
                        await share_btn.evaluate("el => el.click()")
                    logger.info("Instagram share clicked!")
                    await asyncio.sleep(12)

                await browser.close()
                return {"success": True, "platform": "instagram", "message": "Reel shared successfully on Instagram"}
        except Exception as e:
            logger.error(f"Error in Instagram browser upload: {e}")
            return {"success": False, "error": str(e)}

browser_uploader = BrowserUploader()
