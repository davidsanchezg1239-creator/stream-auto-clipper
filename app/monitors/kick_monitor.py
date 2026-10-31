import httpx
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("kick_monitor")

class KickMonitor:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def get_stream_status(self, channel_name: str) -> Dict[str, Any]:
        """
        Checks if a Kick channel is currently live.
        Queries Kick public channel endpoint.
        """
        slug = channel_name.lower().strip()
        url = f"https://kick.com/api/v2/channels/{slug}"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=self.headers, follow_redirects=True) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    livestream = data.get("livestream")
                    user = data.get("user", {})
                    
                    if livestream is not None and livestream.get("is_live", False):
                        categories = livestream.get("categories", [{}])
                        game_name = categories[0].get("name", "Just Chatting") if categories else "General"
                        return {
                            "is_live": True,
                            "channel_id": data.get("id"),
                            "user_name": user.get("username", slug),
                            "avatar_url": user.get("profile_pic"),
                            "title": livestream.get("session_title", ""),
                            "game_name": game_name,
                            "viewer_count": livestream.get("viewer_count", 0),
                            "started_at": livestream.get("created_at"),
                            "thumbnail_url": livestream.get("thumbnail", {}).get("url"),
                        }
                    else:
                        return {
                            "is_live": False,
                            "channel_name": slug,
                            "avatar_url": user.get("profile_pic"),
                            "display_name": user.get("username", slug)
                        }
                elif res.status_code == 404:
                    logger.warning(f"Kick channel not found: {slug}")
                    return {"is_live": False, "error": "Channel not found"}
                else:
                    logger.error(f"Error querying Kick status for {slug}: HTTP {res.status_code}")
                    return {"is_live": False, "error": f"HTTP {res.status_code}"}
        except Exception as e:
            logger.error(f"Exception checking Kick stream for {slug}: {e}")
            return {"is_live": False, "error": str(e)}

    async def fetch_recent_clips(self, channel_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Fetches recently created clips from the Kick channel.
        """
        slug = channel_name.lower().strip()
        url = f"https://kick.com/api/v2/channels/{slug}/clips"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=self.headers, follow_redirects=True) as client:
                res = await client.get(url, params={"sort": "date", "time": "day"})
                if res.status_code == 200:
                    clips_data = res.json().get("clips", [])
                    return clips_data[:limit]
        except Exception as e:
            logger.error(f"Error fetching Kick clips for {slug}: {e}")
        return []
