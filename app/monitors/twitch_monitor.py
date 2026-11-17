import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from app.config import settings

logger = logging.getLogger("twitch_monitor")

class TwitchMonitor:
    def __init__(self):
        self.client_id = settings.TWITCH_CLIENT_ID
        self.client_secret = settings.TWITCH_CLIENT_SECRET
        self.access_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

    async def _ensure_token(self) -> bool:
        """Obtains or refreshes app access token from Twitch OAuth2."""
        if not self.client_id or not self.client_secret:
            logger.warning("Twitch Client ID or Secret is not configured.")
            return False

        # If token exists and is valid, reuse it
        if self.access_token and self.token_expiry and datetime.now(timezone.utc) < self.token_expiry:
            return True

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    self.access_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self.token_expiry = datetime.now(timezone.utc)
                    logger.info("Successfully obtained Twitch OAuth App Access Token.")
                    return True
                else:
                    logger.error(f"Failed to get Twitch token: {res.status_code} - {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error requesting Twitch token: {e}")
            return False

    async def get_stream_status(self, channel_name: str) -> Dict[str, Any]:
        """
        Checks if a twitch channel is currently live.
        Returns dict with: is_live, title, game_name, viewer_count, started_at, user_id.
        """
        has_token = await self._ensure_token()
        if not has_token:
            return {"is_live": False, "error": "Missing Twitch API Credentials"}

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        url = f"https://api.twitch.tv/helix/streams?user_login={channel_name.lower().strip()}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    if data:
                        stream = data[0]
                        return {
                            "is_live": True,
                            "user_id": stream.get("user_id"),
                            "user_name": stream.get("user_name"),
                            "title": stream.get("title"),
                            "game_name": stream.get("game_name"),
                            "viewer_count": stream.get("viewer_count"),
                            "started_at": stream.get("started_at"),
                            "thumbnail_url": stream.get("thumbnail_url"),
                        }
                    else:
                        return {"is_live": False, "channel_name": channel_name}
                else:
                    logger.error(f"Error checking stream status for {channel_name}: {res.status_code} {res.text}")
                    return {"is_live": False, "error": res.text}
        except Exception as e:
            logger.error(f"Exception checking stream status for {channel_name}: {e}")
            return {"is_live": False, "error": str(e)}

    async def get_user_info(self, channel_name: str) -> Optional[Dict[str, Any]]:
        """Gets user profile information including avatar and user ID."""
        has_token = await self._ensure_token()
        if not has_token:
            return None

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        url = f"https://api.twitch.tv/helix/users?login={channel_name.lower().strip()}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    if data:
                        return data[0]
        except Exception as e:
            logger.error(f"Error fetching Twitch user info for {channel_name}: {e}")
        return None

    async def fetch_recent_clips(
        self,
        broadcaster_id: str,
        started_at: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetches newly created clips for broadcaster.
        If started_at is not provided, defaults to the last 48 hours to capture trending viral clips.
        Results are sorted by view_count descending.
        """
        has_token = await self._ensure_token()
        if not has_token:
            return []

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        # If no stream start time is provided, default to last 48 hours
        query_started_at = started_at
        if not query_started_at:
            query_started_at = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params: Dict[str, Any] = {
            "broadcaster_id": broadcaster_id,
            "first": max(limit, 10),
            "started_at": query_started_at
        }

        url = "https://api.twitch.tv/helix/clips"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, headers=headers, params=params)
                if res.status_code == 200:
                    clips = res.json().get("data", [])
                    # Sort by view_count descending so the most viral clip is picked first
                    clips.sort(key=lambda x: x.get("view_count", 0), reverse=True)
                    return clips[:limit]
        except Exception as e:
            logger.error(f"Error fetching clips for broadcaster {broadcaster_id}: {e}")
        return []
