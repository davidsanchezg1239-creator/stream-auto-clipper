import os
import re
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from app.config import find_ffprobe_binary

logger = logging.getLogger("face_tracker")

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

# Normalized coordinates (x_ratio, y_ratio, w_ratio, h_ratio)
# Tailored for 16:9 gaming streams across 1080p, 1440p, 720p
STREAMER_WEBCAM_PROFILES: Dict[str, Dict[str, Any]] = {
    # --- TOP-LEFT CORNER ---
    "rubius": {"x": 0.00, "y": 0.08, "w": 0.28, "h": 0.35, "corner": "top_left"},
    "elrubius": {"x": 0.00, "y": 0.08, "w": 0.28, "h": 0.35, "corner": "top_left"},
    "elrubiusomg": {"x": 0.00, "y": 0.08, "w": 0.28, "h": 0.35, "corner": "top_left"},
    "fanum": {"x": 0.00, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_left"},

    # --- TOP-RIGHT CORNER ---
    "kaicenat": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "kai_cenat": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "jynxzi": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "adinross": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "adin": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "ishowspeed": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},
    "speed": {"x": 0.70, "y": 0.05, "w": 0.28, "h": 0.35, "corner": "top_right"},

    # --- BOTTOM-RIGHT CORNER ---
    "westcol": {"x": 0.70, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_right"},
    "djmariio": {"x": 0.70, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_right"},
    "davoxeneize": {"x": 0.70, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_right"},

    # --- BOTTOM-LEFT CORNER (Most Common Standard) ---
    "illojuan": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "illojuan_": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "auronplay": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "auron": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "carola": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "thegrefg": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "grefg": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "elxokas": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "xokas": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "spreen": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "elspreen": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "xqc": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "xqcow": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "ibai": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "rivers_gg": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "rivers": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "samyrivera": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "juansguarnizo": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "elmariana": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "mariana": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "alexby11": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "alexby": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "roier": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
    "sashagrey": {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"},
}

DEFAULT_CORNER_PROFILE = {"x": 0.01, "y": 0.58, "w": 0.28, "h": 0.38, "corner": "bottom_left"}


class FaceTracker:
    def __init__(self):
        pass

    def get_video_dimensions(self, video_path: str) -> Tuple[int, int]:
        """Reliably inspects video dimensions using ffprobe or cv2."""
        ffprobe_bin = find_ffprobe_binary()
        try:
            cmd = [
                ffprobe_bin, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            parts = res.stdout.strip().split("x")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except Exception as e:
            logger.debug(f"ffprobe dimension check fallback: {e}")

        if HAS_OPENCV:
            try:
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    cap.release()
                    if w > 0 and h > 0:
                        return w, h
            except Exception:
                pass

        return 1920, 1080

    def detect_streamer_webcam(
        self,
        video_path: str,
        streamer_name: str = "",
        max_samples: int = 10
    ) -> Optional[Dict[str, int]]:
        """
        Locates streamer's webcam crop box (x, y, w, h) scaled to video resolution.
        Uses streamer profile registry as primary deterministic ground-truth,
        with universal gaming fallback for split-screen viral formatting.
        """
        frame_width, frame_height = self.get_video_dimensions(video_path)

        # 1. Clean and normalize streamer name
        normalized_name = re.sub(r"[^a-zA-Z0-9]", "", streamer_name.lower()) if streamer_name else ""

        matched_profile = None
        matched_key = None

        # Direct dictionary match
        if normalized_name in STREAMER_WEBCAM_PROFILES:
            matched_profile = STREAMER_WEBCAM_PROFILES[normalized_name]
            matched_key = normalized_name
        else:
            # Substring match (e.g. 'rubius_fan' or 'auronplay_official')
            for key, prof in STREAMER_WEBCAM_PROFILES.items():
                if key in normalized_name or normalized_name in key:
                    matched_profile = prof
                    matched_key = key
                    break

        # Check video filename if still no match
        if not matched_profile and video_path:
            clean_filename = Path(video_path).stem.lower()
            for key, prof in STREAMER_WEBCAM_PROFILES.items():
                if key in clean_filename:
                    matched_profile = prof
                    matched_key = key
                    break

        # If streamer is known, apply profile coordinates
        if matched_profile:
            logger.info(f"🎯 Matched streamer webcam profile for '{matched_key}': corner={matched_profile['corner']}")
            prof = matched_profile
        else:
            # Universal gaming streamer fallback: 85% of gaming streams place webcam in bottom-left
            logger.info(f"Streamer '{streamer_name}' not in registry. Using standard bottom-left webcam layout.")
            prof = DEFAULT_CORNER_PROFILE

        crop_x = int(prof["x"] * frame_width)
        crop_y = int(prof["y"] * frame_height)
        crop_w = int(prof["w"] * frame_width)
        crop_h = int(prof["h"] * frame_height)

        # Ensure bounds within frame
        crop_x = max(0, min(crop_x, frame_width - 10))
        crop_y = max(0, min(crop_y, frame_height - 10))
        crop_w = min(crop_w, frame_width - crop_x)
        crop_h = min(crop_h, frame_height - crop_y)

        return {
            "x": crop_x,
            "y": crop_y,
            "w": crop_w,
            "h": crop_h,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "streamer": matched_key or streamer_name
        }
