import os
import json
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings, find_ffmpeg_binary

logger = logging.getLogger("transcriber")

class AudioTranscriber:
    def __init__(self):
        self.model_size = settings.WHISPER_MODEL_SIZE
        self.device = settings.WHISPER_DEVICE
        self._model = None
        self.ffmpeg_bin = find_ffmpeg_binary()

    def _get_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                logger.info(f"Loading Faster-Whisper model ({self.model_size}) on {self.device}...")
                self._model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
            except ImportError:
                logger.warning("faster-whisper is not installed. Subtitle transcription will run in fallback mode.")
                return None
            except Exception as e:
                logger.error(f"Error loading Whisper model: {e}")
                return None
        return self._model

    def extract_audio(self, video_path: str) -> Optional[str]:
        """Extracts 16kHz mono wav audio from video using FFmpeg."""
        wav_path = str(Path(video_path).with_suffix(".wav"))
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if Path(wav_path).exists():
                return wav_path
        except Exception as e:
            logger.error(f"Failed to extract audio from {video_path}: {e}")
        return None

    async def transcribe(self, video_path: str) -> Dict[str, Any]:
        """
        Transcribes the video asynchronously.
        Returns:
            {
               "full_text": str,
               "segments": [ {"start": 0.0, "end": 2.5, "text": "...", "words": [...] } ]
            }
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, video_path)

    def _transcribe_sync(self, video_path: str) -> Dict[str, Any]:
        wav_path = self.extract_audio(video_path)
        if not wav_path or not Path(wav_path).exists():
            return {
                "full_text": "",
                "segments": [],
                "error": "Could not extract audio"
            }

        model = self._get_model()
        if model is None:
            # Fallback if faster-whisper is not installed yet
            return {
                "full_text": "Momento destacado del stream.",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 5.0,
                        "text": "¡Momento épico del directo!",
                        "words": [
                            {"word": "¡Momento", "start": 0.0, "end": 1.0},
                            {"word": "épico", "start": 1.0, "end": 2.0},
                            {"word": "del", "start": 2.0, "end": 2.5},
                            {"word": "directo!", "start": 2.5, "end": 4.0}
                        ]
                    }
                ],
                "fallback": True
            }

        try:
            segments_generator, info = model.transcribe(wav_path, word_timestamps=True, beam_size=5)
            full_text_list = []
            segments_list = []

            for segment in segments_generator:
                full_text_list.append(segment.text.strip())
                words = []
                if segment.words:
                    for w in segment.words:
                        words.append({
                            "word": w.word.strip(),
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "probability": round(w.probability, 2)
                        })

                segments_list.append({
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                    "words": words
                })

            # Clean up temporary wav file
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

            return {
                "full_text": " ".join(full_text_list),
                "segments": segments_list,
                "language": info.language
            }
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return {"full_text": "", "segments": [], "error": str(e)}
