import json
import logging
import httpx
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("ai_analyzer")

class ClipAnalyzer:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY

    def is_gta6_content(self, game_name: str, title: str, transcript: str) -> bool:
        """Detects whether content is related to GTA 6 / Grand Theft Auto VI."""
        combined = f"{game_name} {title} {transcript}".lower()
        keywords = ["gta 6", "gta vi", "gta6", "gtavi", "grand theft auto vi", "grand theft auto 6", "vice city", "lucia", "jason"]
        return any(k in combined for k in keywords)

    async def analyze_clip(
        self,
        transcript: str,
        original_title: str = "",
        streamer_name: str = "",
        game_name: str = ""
    ) -> Dict[str, Any]:
        """
        Uses Gemini to evaluate clip virality, generate viral title, hook, and hashtags,
        with specialized high-conversion prompts for GTA 6.
        """
        api_key = settings.GEMINI_API_KEY or self.api_key
        if not api_key:
            logger.info("GEMINI_API_KEY is not set in .env. Generating heuristic analysis.")
            return self._heuristic_analysis(transcript, original_title, streamer_name, game_name)

        is_gta6 = self.is_gta6_content(game_name, original_title, transcript)

        if is_gta6:
            special_instructions = """
ATENCIÓN ESPECIAL: Este clip es sobre GRAND THEFT AUTO VI (GTA 6).
- Optimiza el título para máxima viralidad en el lanzamiento mundial de GTA 6.
- Haz énfasis en las novedades: gráficos hiperrealistas, físicas de vehículos, misiones de Jason y Lucia, persecuciones de policía con 5 estrellas, bugs graciosos, o momentos de locura en Vice City.
- Incluye siempre hashtags oficiales de GTA 6 (#GTA6 #GTAVI #ViceCity #GrandTheftAutoVI #GTA6Clips #Viral).
"""
        else:
            special_instructions = ""

        prompt = f"""
Eres un editor y estratega de contenido viral experto en TikTok, Instagram Reels y YouTube Shorts para streamers de Twitch y Kick.
Analiza la siguiente información de un clip:

Streamer: {streamer_name or 'Creador'}
Juego / Categoría: {game_name or 'Variado'}
Título original: {original_title}
Transcripción del audio:
\"\"\"{transcript or 'Sin audio hablado discernible'}\"\"\"

{special_instructions}

Instrucciones:
1. Evalúa el potencial viral del momento (del 1 al 10). {'(Si es de GTA 6, suma +1 punto por tendencia extrema)' if is_gta6 else ''}
2. Clasifica el clip en una sola categoría: "funny" (gracioso), "rage" (enojo/enfado), "clutch" (jugada épica), "fail" (error/ridículo), "story" (anécdota) o "chat" (interacción).
3. Escribe un TÍTULO VIRAL súper atractivo en español (máximo 60 caracteres, con gancho impactante y 1 emoji).
4. Escribe una DESCRIPCIÓN corta (1 a 2 frases) que incite a comentar.
5. Lista 5 a 8 HASHTAGS clave sin espacios (#shorts #twitch #clips ...).
6. ¿Recomiendas publicarlo automáticamente? (true si el score es >= 7.0, false si es aburrido).

Responde EXCLUSIVAMENTE en formato JSON válido con la siguiente estructura:
{{
  "viral_score": 8.8,
  "category": "funny",
  "viral_title": "¡La primera locura en GTA 6! 😱",
  "description": "¿Vieron las físicas de este choque en Vice City? Comenta qué te pareció.",
  "hashtags": "#GTA6 #GTAVI #ViceCity #GTA6Clips #Shorts #Viral #Gaming",
  "should_publish": true
}}
"""
        # 1. Try gemini-3.5-flash-lite first
        for model_name in ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            if "gemini" in model_name:
                payload["generationConfig"] = {"response_mime_type": "application/json"}

            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    res = await client.post(url, json=payload)
                    if res.status_code == 200:
                        result_json = res.json()
                        candidates = result_json.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            raw_text = next((p["text"] for p in parts if "text" in p and not p.get("thought")), "")
                            if not raw_text and parts and "text" in parts[0]:
                                raw_text = parts[0]["text"]

                            cleaned = raw_text.strip()
                            if cleaned.startswith("```"):
                                lines = cleaned.split("\n")
                                if lines[0].startswith("```"): lines = lines[1:]
                                if lines and lines[-1].startswith("```"): lines = lines[:-1]
                                cleaned = "\n".join(lines).strip()

                            data = json.loads(cleaned)
                            parsed = self._parse_gemini_response(data, original_title)
                            parsed["is_gta6"] = is_gta6
                            return parsed
                    else:
                        logger.warning(f"{model_name} returned status {res.status_code}, trying next model...")
            except Exception as e:
                logger.warning(f"Error querying {model_name}: {e}")

        return self._heuristic_analysis(transcript, original_title, streamer_name, game_name, is_gta6)

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
        game_name: str,
        is_gta6: bool = False
    ) -> Dict[str, Any]:
        """Fallback analysis when Gemini API is unavailable."""
        if is_gta6:
            return {
                "score": 9.2,
                "category": "clutch",
                "title": f"¡{streamer_name} en GTA 6 es una locura! 🔥",
                "description": f"¡Lo que acaba de pasar en GTA 6 en directo con {streamer_name}! ¿Qué te parece Vice City?",
                "hashtags": "#GTA6 #GTAVI #GrandTheftAutoVI #ViceCity #GTA6Clips #Gaming #Shorts #TikTok",
                "should_publish": True,
                "is_gta6": True
            }

        title = original_title or (f"Momento increíble de {streamer_name}" if streamer_name else "¡Tienes que ver esto!")
        if len(title) > 55:
            title = title[:52] + "..."

        return {
            "score": 7.5,
            "category": "funny",
            "title": f"¡{title}! 🔥",
            "description": f"Lo mejor del directo de {streamer_name or 'Twitch/Kick'}. ¡Sígueme para más clips diarios!",
            "hashtags": f"#shorts #{streamer_name.lower() or 'streamer'} #gaming #twitchclips #tiktok #reels",
            "should_publish": True,
            "is_gta6": False
        }
