from pathlib import Path
from typing import List, Dict, Any

class SubtitleGenerator:
    """
    Generates high-engagement, modern ASS subtitles (TikTok / Shorts style)
    with highlighted active words, bold styling, and black border.
    """

    def __init__(self, font_name: str = "Arial Black", font_size: int = 68):
        self.font_name = font_name
        self.font_size = font_size

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Converts float seconds (e.g. 72.35) to ASS format: H:MM:SS.cs"""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int(round((seconds - int(seconds)) * 100))
        if centisecs >= 100:
            centisecs = 99
        return f"{hrs}:{mins:02d}:{secs:02d}.{centisecs:02d}"

    def generate_ass(self, segments: List[Dict[str, Any]], output_path: str, style: str = "default") -> str:
        """
        Generates an .ass subtitle file with word-level animated highlighting.
        Supports styles:
        - "default": Classic TikTok white text with yellow active word highlight.
        - "vice_city": GTA 6 / Vice City neon aesthetic (Neon Cyan / Crisp White with Hot Pink highlight).
        """
        is_vc = (style == "vice_city")
        font_size = self.font_size + (4 if is_vc else 0)
        outline_size = 6 if is_vc else 5
        margin_v = 640 if is_vc else 620
        
        # ASS Color format: &HAABBGGRR
        primary_color = "&H00FFFFFF"  # White
        active_color = r"{\c&H00E812FF\b1}" if is_vc else r"{\c&H0000FFFF\b1}"  # Vice City Neon Pink or Yellow
        reset_color = r"{\c&H00FFFFFF\b1}"

        header = f"""[Script Info]
Title: TikTok Viral Subtitles - {"Vice City Edition" if is_vc else "Standard"}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{self.font_name},{font_size},{primary_color},&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline_size},3,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []

        # Process each segment
        for seg in segments:
            words = seg.get("words", [])
            if not words:
                # If no word-level timestamps, display whole sentence
                start_t = self._seconds_to_ass_time(seg.get("start", 0))
                end_t = self._seconds_to_ass_time(seg.get("end", 0))
                text = seg.get("text", "").upper()
                events.append(f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{text}")
                continue

            # Group words into small bite-sized chunks (3 to 5 words max)
            chunk_size = 4
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                if not chunk:
                    continue

                chunk_start = chunk[0]["start"]
                chunk_end = chunk[-1]["end"]

                # For each word in the chunk, produce a timed dialogue line with that word highlighted
                for w_idx, current_w in enumerate(chunk):
                    w_start = self._seconds_to_ass_time(current_w["start"])
                    w_end = self._seconds_to_ass_time(current_w["end"])

                    text_parts = []
                    for idx, w in enumerate(chunk):
                        word_str = w["word"].upper()
                        if idx == w_idx:
                            # Highlighted active word
                            text_parts.append(f"{active_color}{word_str}{reset_color}")
                        else:
                            # Regular white text
                            text_parts.append(word_str)

                    formatted_text = " ".join(text_parts)
                    events.append(f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{formatted_text}")

        content = header + "\n".join(events) + "\n"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path
