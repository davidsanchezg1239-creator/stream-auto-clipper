import os
import asyncio
import logging
from pathlib import Path
from app.config import settings, BASE_DIR

logger = logging.getLogger("youtube_publisher")

class YouTubePublisher:
    def __init__(self):
        self.secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
        self.token_file = settings.YOUTUBE_TOKEN_FILE
        self.scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly"
        ]
        self.service = None

    def _get_authenticated_service(self):
        if self.service:
            return self.service

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if self.token_file.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_file), self.scopes)

            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired YouTube OAuth token...")
                creds.refresh(Request())
                with open(self.token_file, "w", encoding="utf-8") as token:
                    token.write(creds.to_json())

            if not creds or not creds.valid:
                if self.secrets_file.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.secrets_file), self.scopes)
                    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
                    with open(self.token_file, "w", encoding="utf-8") as token:
                        token.write(creds.to_json())
                else:
                    logger.warning(f"YouTube client secrets file not found: {self.secrets_file}")
                    return None

            self.service = build("youtube", "v3", credentials=creds)
            return self.service
        except Exception as e:
            logger.error(f"Failed to authenticate with YouTube API: {e}")
            return None

    async def upload_video(
        self,
        file_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        is_short: bool = True,
        privacy_status: str = "public"
    ) -> Dict[str, Any]:
        """
        Uploads video to YouTube (as a Short or standard long-form video).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._upload_video_sync,
            file_path,
            title,
            description,
            tags or [],
            is_short,
            privacy_status
        )

    def _upload_video_sync(
        self,
        file_path: str,
        title: str,
        description: str,
        tags: List[str],
        is_short: bool,
        privacy_status: str
    ) -> Dict[str, Any]:
        target_path = Path(file_path)
        if not target_path.is_absolute():
            target_path = BASE_DIR / target_path

        if not target_path.exists():
            return {"success": False, "error": f"Video file not found: {file_path}"}

        service = self._get_authenticated_service()
        if not service:
            logger.warning("YouTube API service not authenticated. Simulated upload.")
            return {
                "success": False,
                "simulated": True,
                "error": "YouTube credentials missing. Place client_secret.json in credentials/ directory."
            }

        try:
            from googleapiclient.http import MediaFileUpload

            final_title = f"{title} #Shorts" if is_short and "#Shorts" not in title else title
            final_desc = f"{description}\n\n#Shorts #Clips" if is_short else description

            body = {
                "snippet": {
                    "title": final_title[:100],
                    "description": final_desc,
                    "tags": tags,
                    "categoryId": "20"  # Gaming Category ID
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(str(target_path), chunksize=-1, resumable=True)
            request = service.videos().insert(part="snippet,status", body=body, media_body=media)
            response = request.execute()

            video_id = response.get("id")
            video_url = f"https://www.youtube.com/shorts/{video_id}" if is_short else f"https://youtu.be/{video_id}"

            logger.info(f"Successfully uploaded to YouTube: {video_url}")
            return {
                "success": True,
                "video_id": video_id,
                "url": video_url,
                "title": final_title
            }
        except Exception as e:
            logger.error(f"Error uploading video to YouTube: {e}")
            return {"success": False, "error": str(e)}
