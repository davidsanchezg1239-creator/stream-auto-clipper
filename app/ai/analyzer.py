import json
import logging
import httpx
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("ai_analyzer")

class ClipAnalyzer:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY

    def is_any_gta_content(self, game_name: str, title: str, transcript: str) -> bool:
        """Detects whether content is related to ANY Grand Theft Auto game (GTA V, GTA RP, or GTA VI)."""
        combined = f"{game_name} {title} {transcript}".lower()
        gta_broad_keywords = [
            "grand theft auto", "gta", "vice city", "vicecity", "rockstar games", "rockstar",
            "nopixel", "marbella vice", "spainrp", "london rp", "roleplay", "gtarp",
            "atraco", "persecucion", "persecución", "5 estrellas", "los santos",
            "lucia", "jason", "leonida"
        ]
        return any(k in combined for k in gta_broad_keywords)

    def is_gta6_content(self, game_name: str, title: str, transcript: str) -> bool:
        """Detects whether content is specifically related to GTA 6 / Grand Theft Auto VI / Vice City."""
        combined = f"{game_name} {title} {transcript}".lower()
        keywords = [
            "gta 6", "gta vi", "gta6", "gtavi", "grand theft auto vi", "grand theft auto 6",
            "vice city", "vicecity", "lucia", "jason", "leonida", "rockstar games", "rockstar",
            "trailer 2", "gta online", "gta roleplay", "gta rp", "marbella vice", "spainrp",
            "london rp", "nopixel", "atraco", "persecucion", "persecución", "5 estrellas",
            "cinco estrellas", "vice city roleplay", "gtarp"
        ]
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
        # 1. Try blazing fast Gemini call with 3.5s timeout
        for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            if "gemini" in model_name:
                payload["generationConfig"] = {"response_mime_type": "application/json"}

            try:
                async with httpx.AsyncClient(timeout=3.5) as client:
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
            except Exception as e:
                logger.debug(f"Fast AI attempt {model_name} bypassed: {e}")

        return self.generate_smart_viral_title(original_title, streamer_name, game_name, transcript)

    def _parse_gemini_response(self, data: dict, original_title: str) -> dict:
        return {
            "score": float(data.get("viral_score", data.get("score", 8.0))),
            "category": data.get("category", "entertainment"),
            "title": data.get("viral_title", data.get("title", original_title or "¡Momento épico!")),
            "description": data.get("description", ""),
            "hashtags": data.get("hashtags", "#shorts #clips #viral"),
            "should_publish": bool(data.get("should_publish", True))
        }

    def generate_smart_viral_title(
        self,
        original_title: str = "",
        streamer_name: str = "",
        game_name: str = "",
        transcript: str = ""
    ) -> Dict[str, Any]:
        """
        High-Conversion Viral Engine: Generates click-worthy, algorithm-friendly titles
        in Spanish specifically tuned for YouTube Shorts, TikTok, and Instagram Reels algorithms.
        """
        import re
        raw_s = (streamer_name or "").strip()
        # Clean streamer name: "Fanum (AMP)" -> "Fanum"
        clean_s = re.sub(r'\(.*?\)', '', raw_s).strip()
        s_upper = clean_s.upper() if clean_s else ""
        s_lower = clean_s.lower()

        t_clean = (original_title or "").strip()
        # Remove streamer name prefixes if present in original title ("carola - ...")
        t_text = re.sub(r'^(?:[\w\s]+[:\-]\s*)', '', t_clean).lower()
        combined = f"{t_text} {transcript or ''}".lower()

        is_gta = self.is_gta6_content(game_name, original_title, transcript) or self.is_any_gta_content(game_name, original_title, transcript)

        if is_gta:
            # 1. First time / loading / starting
            if any(k in combined for k in ["first time", "primera vez", "loads", "starts", "inicia", "comienza", "empezando", "playthrough"]):
                title = f"¡{s_upper} PRUEBA GTA 6 POR PRIMERA VEZ! 🌴😱" if s_upper else "¡PRIMERA VEZ JUGANDO A GTA 6! 🌴😱"
            # 2. Lucia / Jason / characters
            elif "lucia" in combined:
                title = f"¡{s_upper} REACCIONA A LUCIA EN GTA 6! 🚨🔥" if s_upper else "¡LUCIA EN ACCIÓN EN GTA 6! 🚨🔥"
            elif "jason" in combined:
                title = f"¡JASON Y LUCIA EN ACCIÓN EN GTA 6! 🚗💨"
            # 3. Dominican / specific cultural hype
            elif "dominican" in combined or "rd" in combined:
                title = f"¡DOMINICANO SUELTO EN VICE CITY! GTA 6 🇩🇴🔥"
            # 4. Babies in GTA
            elif any(k in combined for k in ["baby", "babys", "bebe", "bebé"]):
                title = f"¡KAI CENAT ENCUENTRA UN BEBÉ EN GTA 6! 👶💀" if "kai" in s_lower else "¡HAY BEBÉS EN GTA 6! 👶😱"
            # 5. Police / Cops / SWAT / 5 stars
            elif any(k in combined for k in ["police", "policia", "policía", "cop", "swat", "5 estrellas", "cinco estrellas", "persecucion", "persecución", "arrest"]):
                title = "¡LA POLICÍA DE GTA 6 NO TIENE PIEDAD! 🚨💀"
            # 6. Stealing cars / Heist
            elif any(k in combined for k in ["steal", "roba", "robando", "carro", "coche", "atraco", "heist"]):
                title = f"¡{s_upper} ROBA SU PRIMER COCHE EN GTA 6! 🏎️💨" if s_upper else "¡ROBANDO EL PRIMER COCHE EN GTA 6! 🏎️💨"
            # 7. Roleplay / Rol
            elif re.search(r'\b(?:rol|roleplay|rp)\b', combined):
                title = f"¡{s_upper} HACE ROLEPLAY EN GTA 6 Y ES CINE! 🎭🔥" if s_upper else "¡EL ROLEPLAY EN GTA 6 ES CINE PURO! 🎭🔥"
            # 8. Graphics / Florida / Realism
            elif any(k in combined for k in ["graphic", "grafico", "gráfico", "florida", "real", "visual", "look", "hype"]):
                title = f"¡{s_upper} SE VUELVE LOCO CON LOS GRÁFICOS DE GTA 6! 🤯🌴" if s_upper else "¡LOS GRÁFICOS DE GTA 6 SON DE OTRA ÉPOCA! 🤯🌴"
            # 9. Opps / Mission / First mission
            elif any(k in combined for k in ["opp", "opps", "mission", "mision", "misión"]):
                title = f"¡PRIMERA MISIÓN DE GTA 6 Y TERMINA ASÍ! 💀🚓"
            # 10. Tears / Crying / Emotional
            elif any(k in combined for k in ["cry", "llorar", "lagrimas", "emocion", "quiero llorar"]):
                title = f"¡{s_upper} CASI LLORA DE LA EMOCIÓN CON GTA 6! 😭🌴" if s_upper else "¡MOMENTO EMOTIVO EN GTA 6! 😭🌴"
            # 11. Long awaited release / Extensible
            elif any(k in combined for k in ["llegó el día", "llego el dia", "extensible", "espera"]):
                title = f"¡LLEGÓ EL DÍA! {s_upper} JUEGA GTA 6 TRAS AÑOS DE ESPERA ✨🌴" if s_upper else "¡LLEGÓ EL DÍA DE GTA 6! ✨🌴"
            # 12. Strip Club / Nightlife
            elif any(k in combined for k in ["strip", "club", "dance", "baile"]):
                title = "¡VISITANDO EL STRIP CLUB EN GTA 6! 🔞🌴"
            # 13. Bugs / Glitches / Physics
            elif any(k in combined for k in ["bug", "glitch", "fisica", "fisicas"]):
                title = "¡EL PRIMER BUG ÉPICO DE GTA 6! 😂🌴"
            # 14. NPC interactions / Hilarious moments
            elif any(k in combined for k in ["saludo", "npc", "exitado", "locura", "loco", "wtf"]):
                title = f"¡{s_upper} NO SE PUEDE CREER ESTO EN GTA 6! 😂🌴" if s_upper else "¡UN NPC HACE ESTO EN GTA 6! 💀😂"
            else:
                if s_upper:
                    title = f"¡{s_upper} HACE HISTORIA EN GTA 6! 🔥🌴"
                else:
                    title = f"¡EL MOMENTO MÁS VIRAL DE GTA 6! 🌴🔥"

            return {
                "score": 9.6,
                "category": "clutch" if any(k in combined for k in ["mision", "misión", "police", "atraco"]) else "funny",
                "title": title,
                "description": f"¿Qué opinas de este momentazo de {clean_s or 'GTA 6'} en Vice City? ¡Comenta abajo y suscríbete para los mejores clips diarios de GTA VI! 🌴🎮",
                "hashtags": "#GTA6 #GTAVI #GrandTheftAutoVI #ViceCity #GTA6Clips #Viral #Gaming #Shorts #TikTok #Reels #FYP",
                "should_publish": True,
                "is_gta6": True
            }

        # Non-GTA viral generator
        if "rubius" in s_lower:
            title = f"¡RUBIUS LA VUELVE A LIAR EN DIRECTO! 😂🔥"
        elif "illojuan" in s_lower:
            title = f"¡ILLOJUAN NO AGUANTA LA RISA CON ESTO! 💀😂"
        elif "xokas" in s_lower or "elxokas" in s_lower:
            title = f"¡ELXOKAS SE CABREA EN DIRECTO! 🤬🔥"
        elif "thegrefg" in s_lower:
            title = f"¡THEGREFG EN UN MOMENTO ÉPICO! 😱🔥"
        elif "auron" in s_lower:
            title = f"¡AURONPLAY TOTALMENTE BASADO! 😂✨"
        elif "ibai" in s_lower:
            title = f"¡IBAI SE QUEDA SIN PALABRAS! 🤯🔥"
        elif "westcol" in s_lower:
            title = f"¡WESTCOL NO TIENE FILTRO EN ESTE CLIP! 💀🔥"
        elif "kai" in s_lower:
            title = f"¡KAI CENAT HACE ESTA LOCURA EN STREAM! 😱🔥"
        elif "xqc" in s_lower:
            title = f"¡XQC PIERDE LA CABEZA EN VIVO! 💀😂"
        elif "spreen" in s_lower:
            title = f"¡SPREEN CON UNA JUGADA IMPOSIBLE! 🏆🔥"
        elif "rivers" in s_lower:
            title = f"¡RIVERS SE ENFADA EN DIRECTO! 😂🔥"
        else:
            base = t_clean or f"Momento increíble de {clean_s}"
            if len(base) > 50:
                base = base[:47] + "..."
            title = f"¡{base}! 🔥"

        return {
            "score": 8.0,
            "category": "funny",
            "title": title,
            "description": f"Lo mejor del directo de {clean_s or 'Twitch/Kick'}. ¡Sígueme para no perderte ningún clip viral diario!",
            "hashtags": f"#shorts #{clean_s.lower() or 'streamer'} #gaming #twitchclips #tiktok #reels #viral #fyp",
            "should_publish": True,
            "is_gta6": False
        }

    def _heuristic_analysis(
        self,
        transcript: str,
        original_title: str,
        streamer_name: str,
        game_name: str,
        is_gta6: bool = False
    ) -> Dict[str, Any]:
        return self.generate_smart_viral_title(original_title, streamer_name, game_name, transcript)
