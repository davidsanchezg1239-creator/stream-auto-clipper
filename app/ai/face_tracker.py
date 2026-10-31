import os
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("face_tracker")

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger.warning("OpenCV (cv2) not installed. Using heuristic facecam positioning.")

class FaceTracker:
    def __init__(self):
        self.face_cascade = None
        if HAS_OPENCV:
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                if os.path.exists(cascade_path):
                    self.face_cascade = cv2.CascadeClassifier(cascade_path)
            except Exception as e:
                logger.warning(f"Could not load Haar cascade: {e}")


    def detect_streamer_webcam(self, video_path: str, max_samples: int = 10) -> Optional[Dict[str, int]]:
        """
        Samples frames from video to locate streamer's facecam box (x, y, w, h).
        Returns bounding box or None if no face is confidently detected.
        """
        if not HAS_OPENCV or not self.face_cascade:
            # Do not guess blind coordinates to avoid cropping empty walls
            return None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Cannot open video for face tracking: {video_path}")
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if total_frames <= 0:
            cap.release()
            return None

        detected_faces = []
        step = max(1, total_frames // (max_samples + 1))

        for i in range(1, max_samples + 1):
            frame_idx = i * step
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(60, 60),
                maxSize=(frame_width // 2, frame_height // 2)
            )

            for (x, y, w, h) in faces:
                detected_faces.append((x, y, w, h))

        cap.release()

        if not detected_faces:
            logger.info("No face detected in video samples. Fallback layout will be used.")
            return None

        # Take average or most frequent cluster
        avg_x = int(sum(f[0] for f in detected_faces) / len(detected_faces))
        avg_y = int(sum(f[1] for f in detected_faces) / len(detected_faces))
        avg_w = int(sum(f[2] for f in detected_faces) / len(detected_faces))
        avg_h = int(sum(f[3] for f in detected_faces) / len(detected_faces))

        # Add margin around face to capture the full webcam box (e.g., shoulders, microphone)
        margin_x = int(avg_w * 0.6)
        margin_y = int(avg_h * 0.6)
        crop_x = max(0, avg_x - margin_x)
        crop_y = max(0, avg_y - margin_y)
        crop_w = min(frame_width - crop_x, avg_w + margin_x * 2)
        crop_h = min(frame_height - crop_y, avg_h + margin_y * 2)

        return {
            "x": crop_x,
            "y": crop_y,
            "w": crop_w,
            "h": crop_h,
            "frame_width": frame_width,
            "frame_height": frame_height
        }
