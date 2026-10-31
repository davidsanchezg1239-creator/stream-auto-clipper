import json
import logging
import httpx
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("ai_analyzer")

class ClipAnalyzer:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                # httpx REST fallback will be used automatically
                pass

    async def analyze_clip(
        self,
        transcript: str,
        original_title: str = "",
        streamer_name: str = "",
        game_name: str = ""
    ) -> Dict[str, Any]:
        """
        Uses Gemini to evaluate clip virality, generate viral title, hook, and hashtags.
        """
        # Always re-read settings in case .env was updated
        api_key = settings.GEMINI_API_KEY or self.api_key
        if not api_key:
            logger.info("GEMINI_API_KEY is not set in .env. Generating heuristic analysis.")
            return self._heuristic_analysis(transcript, original_title, streamer_name, game_name)

        prompt = f"""
Eres un editor y estratega de contenido viral experto en TikTok, Instagram Reels y YouTube Shorts para streamers de Twitch y Kick.
Analiza la siguiente información de un clip:

Streamer: {streamer_name or 'Creador'}
Juego / Categoría: {game_name or 'Variado'}
Título original: {original_title}
Transcripción del audio:
\"\"\"{transcript or 'Sin audio hablado discernible'}\"\"\"

Instrucciones:
1. Evalúa el potencial viral del momento (del 1 al 10).
2. Clasifica el clip en una sola categoría: "funny" (gracioso), "rage" (enojo/enfado), "clutch" (jugada épica), "fail" (error/ridículo), "story" (anécdota) o "chat" (interacción).
3. Escribe un TÍTULO VIRAL súper atractivo en español (máximo 60 caracteres, con gancho y 1 emoji).
4. Escribe una DESCRIPCIÓN corta (1 a 2 frases) que incite a comentar.
5. Lista 5 a 8 HASHTAGS clave sin espacios (#shorts #twitch #clips ...).
6. ¿Recomiendas publicarlo automáticamente? (true si el score es >= 6.5, false si es aburrido).

Responde EXCLUSIVAMENTE en formato JSON válido con la siguiente estructura:
{{
  "viral_score": 8.5,
  "category": "funny",
  "viral_title": "¡No te vas a creer lo que pasó! 😱",
  "description": "Momentos que solo pasan en vivo... ¿Qué habrías hecho tú?",
  "hashtags": "#shorts #twitchclips #streamer #humor #viral #tiktok",
  "should_publish": true
}}
"""
        # Try google-genai client first if present
        if self.client:
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text.strip())
                return self._parse_gemini_response(data, original_title)
            except Exception as e:
                logger.warning(f"google-genai SDK failed, falling back to REST: {e}")

        # Direct REST API call via httpx
        # gemma-4-26b-a4b-it is active, free, and returns rich structured predictions
        model_name = "gemma-4-26b-a4b-it"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    result_json = res.json()
                    candidates = result_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
                        raw_text = text_parts[-1] if text_parts else parts[0].get("text", "{}")
                        
                        # Strip markdown fences if present
                        cleaned = raw_text.strip()
                        if cleaned.startswith("```"):
                            lines = cleaned.split("\n")
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            cleaned = "\n".join(lines).strip()

                        data = json.loads(cleaned)
                        return self._parse_gemini_response(data, original_title)
                else:
                    logger.error(f"Google AI REST error: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.error(f"Google AI request failed: {e}")

        return self._heuristic_analysis(transcript, original_title, streamer_name, game_name)

    def _parse_gemini_response(self, data: dict, original_title: str) -> dict:
        return {
            "score": float(data.get("viral_score", data.get("score", 8.0))),
            "category": data.get("category", "entertainment"),
            "title": data.get("viral_title", data.get("title", original_title or "¡Momento épico!")),
            "description": data.get("description", ""),
            "hashtags": data.get("hashtags", "#shorts #clips #viral"),
            "should_publish": bool(data.get("should_publish", True))
        }

    def _heuristic_analysis(
        self,
        transcript: str,
        original_title: str,
        streamer_name: str,
        game_name: str
    ) -> Dict[str, Any]:
        """Fallback analysis when Gemini API is unavailable."""
        title = original_title or (f"Momento increíble de {streamer_name}" if streamer_name else "¡Tienes que ver esto!")
        if len(title) > 55:
            title = title[:52] + "..."

        return {
            "score": 7.5,
            "category": "funny",
            "title": f"¡{title}! 🔥",
            "description": f"Lo mejor del directo de {streamer_name or 'Twitch/Kick'}. ¡Sígueme para más clips diarios!",
            "hashtags": f"#shorts #{streamer_name.lower() or 'streamer'} #gaming #twitchclips #tiktok #reels",
            "should_publish": True
        }
