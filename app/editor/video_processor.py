import os
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from app.config import settings, find_ffmpeg_binary

logger = logging.getLogger("video_processor")

class VideoProcessor:
    def __init__(self):
        self.ffmpeg_bin = find_ffmpeg_binary()
        self.processed_dir = settings.PROCESSED_DIR

    async def render_vertical_short(
        self,
        input_video: str,
        output_filename: str,
        face_box: Optional[Dict[str, int]] = None,
        subtitle_ass_path: Optional[str] = None,
        layout: str = "auto"
    ) -> Dict[str, Any]:
        """
        Renders a 9:16 vertical video (1080x1920) for YouTube Shorts, Reels, TikTok.
        Layout options:
        - "auto": uses split if face_box is found, otherwise uses blur
        - "blur": ambient blurred background top/bottom with clean 16:9 centered
        - "center": fullscreen 9:16 vertical center crop
        - "split": streamer top + gameplay bottom
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._render_vertical_sync,
            input_video,
            output_filename,
            face_box,
            subtitle_ass_path,
            layout
        )

    def _render_vertical_sync(
        self,
        input_video: str,
        output_filename: str,
        face_box: Optional[Dict[str, int]] = None,
        subtitle_ass_path: Optional[str] = None,
        layout: str = "auto"
    ) -> Dict[str, Any]:
        output_path = str(self.processed_dir / output_filename)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Decide layout
        chosen_layout = layout
        if chosen_layout == "auto":
            if face_box and face_box.get("w", 0) > 120:
                chosen_layout = "split"
            else:
                chosen_layout = "blur"

        # Build video filters based on layout
        if chosen_layout == "split" and face_box:
            fx, fy, fw, fh = face_box["x"], face_box["y"], face_box["w"], face_box["h"]
            filters = [
                "[0:v]split=2[cam_in][game_in]",
                f"[cam_in]crop={fw}:{fh}:{fx}:{fy},scale=1080:640:force_original_aspect_ratio=increase,crop=1080:640[cam]",
                "[game_in]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1280[game]",
                "[cam][game]vstack=inputs=2[base_v]"
            ]
        elif chosen_layout == "center":
            # Direct full-screen vertical zoom on the center
            filters = [
                "[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920[base_v]"
            ]
        else:
            # Default "blur": Beautiful ambient blurred background
            filters = [
                "[0:v]split=2[bg_in][fg_in]",
                "[bg_in]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg]",
                "[fg_in]scale=1080:608:force_original_aspect_ratio=decrease[fg]",
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[base_v]"
            ]

        # Add subtitle burning stage if .ass file exists
        if subtitle_ass_path and Path(subtitle_ass_path).exists():
            clean_sub_path = Path(subtitle_ass_path).resolve().as_posix().replace(":", r"\:")
            filters.append(f"[base_v]subtitles=filename='{clean_sub_path}'[final_v]")
            v_map = "[final_v]"
        else:
            v_map = "[base_v]"

        filter_complex = ";".join(filters)

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", input_video,
            "-filter_complex", filter_complex,
            "-map", v_map,
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "256k",
            "-pix_fmt", "yuv420p",
            output_path
        ]

        logger.info(f"Rendering 9:16 vertical video to: {output_path}")
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return {"success": False, "error": result.stderr}

            if Path(output_path).exists():
                return {
                    "success": True,
                    "output_path": output_path,
                    "file_size": Path(output_path).stat().st_size
                }
            return {"success": False, "error": "Output file not found"}
        except Exception as e:
            logger.error(f"Error during video render: {e}")
            return {"success": False, "error": str(e)}
