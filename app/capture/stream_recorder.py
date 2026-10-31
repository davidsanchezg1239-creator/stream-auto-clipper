import os
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from app.config import settings, find_ffmpeg_binary

logger = logging.getLogger("stream_recorder")

class StreamRecorder:
    def __init__(self):
        self.downloads_dir = settings.DOWNLOADS_DIR
        self.ffmpeg_bin = find_ffmpeg_binary()

    async def download_clip(self, clip_url: str, custom_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Downloads a Twitch or Kick clip using yt-dlp.
        Returns path, duration, title, and resolution.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._download_clip_sync, clip_url, custom_filename)

    def _download_clip_sync(self, clip_url: str, custom_filename: Optional[str] = None) -> Dict[str, Any]:
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp is not installed. Run `pip install yt-dlp`")
            return {"success": False, "error": "yt-dlp is missing"}

        filename = custom_filename or f"clip_{uuid.uuid4().hex[:8]}"
        output_template = str(self.downloads_dir / f"{filename}.%(ext)s")

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
        }

        # If custom ffmpeg is specified and exists, pass it to yt-dlp
        if self.ffmpeg_bin and self.ffmpeg_bin != "ffmpeg":
            ydl_opts["ffmpeg_location"] = str(Path(self.ffmpeg_bin).parent)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clip_url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                # Ensure .mp4 extension
                final_path = Path(downloaded_file).with_suffix(".mp4")
                if not final_path.exists() and Path(downloaded_file).exists():
                    final_path = Path(downloaded_file)

                return {
                    "success": True,
                    "file_path": str(final_path),
                    "duration": info.get("duration", 0),
                    "title": info.get("title", ""),
                    "width": info.get("width", 1920),
                    "height": info.get("height", 1080),
                }
        except Exception as e:
            logger.error(f"Failed to download clip from {clip_url}: {e}")
            return {"success": False, "error": str(e)}

    async def record_live_segment(self, stream_url: str, duration_seconds: int = 600) -> Optional[str]:
        """
        Records a 10-minute segment directly from a live Twitch/Kick stream using streamlink.
        """
        output_filename = f"live_chunk_{uuid.uuid4().hex[:8]}.mp4"
        output_path = self.downloads_dir / output_filename
        
        # Command: streamlink <stream_url> best -o <output_path>
        cmd = [
            "streamlink",
            stream_url,
            "best",
            "-o", str(output_path),
            "--force"
        ]

        logger.info(f"Starting live stream capture for {duration_seconds}s: {stream_url}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Wait for duration or until process ends
            try:
                await asyncio.wait_for(proc.wait(), timeout=duration_seconds)
            except asyncio.TimeoutError:
                # Target duration reached, terminate recording gracefully
                proc.terminate()
                await proc.wait()

            if output_path.exists() and output_path.stat().st_size > 1024 * 500: # at least 500KB
                return str(output_path)
            return None
        except Exception as e:
            logger.error(f"Error capturing stream: {e}")
            return None
