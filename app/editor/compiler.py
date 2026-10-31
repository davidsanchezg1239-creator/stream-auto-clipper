import os
import uuid
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from app.config import settings, find_ffmpeg_binary

logger = logging.getLogger("compiler")

class VideoCompiler:
    def __init__(self):
        self.ffmpeg_bin = find_ffmpeg_binary()
        self.compilations_dir = settings.COMPILATIONS_DIR

    async def compile_long_form(
        self,
        video_paths: List[str],
        output_filename: str = None
    ) -> Dict[str, Any]:
        """
        Stitches multiple clips into a continuous 10-minute (or desired length) YouTube compilation video.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._compile_sync, video_paths, output_filename)

    def _compile_sync(self, video_paths: List[str], output_filename: str = None) -> Dict[str, Any]:
        if not video_paths:
            return {"success": False, "error": "No videos provided for compilation"}

        filename = output_filename or f"compilation_{uuid.uuid4().hex[:8]}.mp4"
        output_path = str(self.compilations_dir / filename)
        concat_list_file = str(self.compilations_dir / f"concat_{uuid.uuid4().hex[:8]}.txt")

        # Create FFmpeg concat demuxer text file
        lines = []
        for v in video_paths:
            if Path(v).exists():
                escaped = Path(v).as_posix().replace("'", r"'\''")
                lines.append(f"file '{escaped}'")

        if not lines:
            return {"success": False, "error": "None of the provided video files exist"}

        with open(concat_list_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path
        ]

        logger.info(f"Compiling {len(lines)} clips into long-form video: {output_path}")
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if os.path.exists(concat_list_file):
                os.remove(concat_list_file)

            if result.returncode != 0:
                logger.error(f"Compilation error: {result.stderr}")
                return {"success": False, "error": result.stderr}

            if Path(output_path).exists():
                file_size = Path(output_path).stat().st_size
                return {
                    "success": True,
                    "output_path": output_path,
                    "file_size": file_size
                }
            return {"success": False, "error": "Compiled file not created"}
        except Exception as e:
            if os.path.exists(concat_list_file):
                os.remove(concat_list_file)
            logger.error(f"Error compiling video: {e}")
            return {"success": False, "error": str(e)}
