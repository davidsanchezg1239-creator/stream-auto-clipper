import httpx
import logging
from typing import Dict, Any, Optional
from app.config import settings
from app.publishers.browser_uploader import browser_uploader

logger = logging.getLogger("social_dispatcher")

class SocialDispatcher:
    def __init__(self):
        self.ayrshare_key = settings.AYRSHARE_API_KEY
        self.instagram_account_id = settings.INSTAGRAM_ACCOUNT_ID
        self.instagram_token = settings.INSTAGRAM_ACCESS_TOKEN
        self.tiktok_token = settings.TIKTOK_ACCESS_TOKEN

    async def publish_all(
        self,
        video_url_or_path: str,
        caption: str,
        hashtags: str = ""
    ) -> Dict[str, Any]:
        """
        Dispatches vertical video to all configured social platforms (TikTok, Instagram Reels, YouTube).
        Uses Ayrshare API if configured (the easiest unified method) or direct endpoints.
        """
        full_text = f"{caption}\n\n{hashtags}".strip()
        results = {}

        # 1. Try Ayrshare if configured
        if self.ayrshare_key:
            ayr_res = await self._publish_via_ayrshare(video_url_or_path, full_text)
            results["ayrshare"] = ayr_res
            return results

        # 2. Instagram
        if self.instagram_account_id and self.instagram_token:
            ig_res = await self._publish_instagram_reel(video_url_or_path, full_text)
            results["instagram"] = ig_res
        elif browser_uploader.is_logged_in("instagram"):
            ig_res = await browser_uploader.upload_instagram_reel(video_url_or_path, full_text)
            results["instagram"] = ig_res
        else:
            results["instagram"] = {"status": "skipped", "reason": "No Instagram session or credentials configured"}

        # 3. TikTok
        if self.tiktok_token:
            tk_res = await self._publish_tiktok(video_url_or_path, full_text)
            results["tiktok"] = tk_res
        elif browser_uploader.is_logged_in("tiktok"):
            tk_res = await browser_uploader.upload_tiktok_reel(video_url_or_path, full_text)
            results["tiktok"] = tk_res
        else:
            results["tiktok"] = {"status": "skipped", "reason": "No TikTok session or token configured"}

        return results

    async def _publish_via_ayrshare(self, video_url: str, post_text: str) -> Dict[str, Any]:
        """Publishes to Instagram, TikTok, and YouTube in 1 call via Ayrshare."""
        url = "https://app.ayrshare.com/api/post"
        headers = {
            "Authorization": f"Bearer {self.ayrshare_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "post": post_text,
            "platforms": ["instagram", "tiktok", "youtube"],
            "mediaUrls": [video_url],
            "shortenLinks": False,
            "autoSchedule": True
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                return res.json()
        except Exception as e:
            logger.error(f"Ayrshare error: {e}")
            return {"status": "error", "error": str(e)}

    async def _publish_instagram_reel(self, video_url: str, caption: str) -> Dict[str, Any]:
        """Direct Instagram Reels publishing container workflow."""
        base_url = f"https://graph.facebook.com/v21.0/{self.instagram_account_id}/media"
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self.instagram_token
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Step 1: Create media container
                res = await client.post(base_url, params=params)
                container_data = res.json()
                creation_id = container_data.get("id")
                if not creation_id:
                    return {"status": "error", "error": container_data}

                # Step 2: Publish media container
                publish_url = f"https://graph.facebook.com/v21.0/{self.instagram_account_id}/media_publish"
                pub_res = await client.post(publish_url, params={"creation_id": creation_id, "access_token": self.instagram_token})
                return pub_res.json()
        except Exception as e:
            logger.error(f"Instagram publishing error: {e}")
            return {"status": "error", "error": str(e)}

    async def _publish_tiktok(self, video_url: str, caption: str) -> Dict[str, Any]:
        """Direct TikTok Content Posting API."""
        # Simulated or endpoint call
        return {
            "status": "pending_manual_or_direct",
            "message": "Ready to dispatch to TikTok once app review is completed."
        }
