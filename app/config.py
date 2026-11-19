import os
import shutil
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8050
    DEBUG: bool = True
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'data' / 'clipper.db'}"

    # Binaries
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"

    # Directories
    DOWNLOADS_DIR: Path = BASE_DIR / "storage" / "downloads"
    PROCESSED_DIR: Path = BASE_DIR / "storage" / "processed"
    COMPILATIONS_DIR: Path = BASE_DIR / "storage" / "compilations"
    CREDENTIALS_DIR: Path = BASE_DIR / "credentials"
    DATA_DIR: Path = BASE_DIR / "data"

    # AI
    GEMINI_API_KEY: str = ""
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "cpu"

    # Twitch
    TWITCH_CLIENT_ID: str = ""
    TWITCH_CLIENT_SECRET: str = ""
    TWITCH_WEBHOOK_SECRET: str = ""

    # YouTube
    YOUTUBE_CLIENT_SECRETS_FILE: Path = BASE_DIR / "credentials" / "client_secret.json"
    YOUTUBE_TOKEN_FILE: Path = BASE_DIR / "credentials" / "youtube_token.json"

    # Socials
    AYRSHARE_API_KEY: str = ""
    INSTAGRAM_ACCOUNT_ID: str = ""
    INSTAGRAM_ACCESS_TOKEN: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""

    # Polling frequency in seconds (3 minutes to avoid flood)
    CHECK_INTERVAL_SECONDS: int = 180
    MAX_CLIPS_PER_SCAN: int = 2

    # Auto-Pilot & GTA 6 Turbo Radar Settings
    AUTO_PUBLISH_VIRAL: bool = False
    AUTO_PUBLISH_MIN_SCORE: float = 8.0
    GTA6_TURBO_ENABLED: bool = True
    GTA6_TURBO_INTERVAL_SECONDS: int = 20

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
for folder in [
    settings.DOWNLOADS_DIR,
    settings.PROCESSED_DIR,
    settings.COMPILATIONS_DIR,
    settings.CREDENTIALS_DIR,
    settings.DATA_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)

def find_ffmpeg_binary() -> str:
    """Finds ffmpeg binary in PATH or common Windows winget/custom locations."""
    which_bin = shutil.which(settings.FFMPEG_PATH)
    if which_bin:
        try:
            return str(Path(which_bin).resolve())
        except Exception:
            return which_bin

    # Common Windows installation paths (Winget, Scoop, Program Files)
    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "ffmpeg" / "bin" / "ffmpeg.exe",
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffmpeg.exe",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                return str(p.resolve())
            except Exception:
                return str(p)
    return settings.FFMPEG_PATH

def find_ffprobe_binary() -> str:
    """Finds ffprobe binary in PATH or common Windows winget/custom locations."""
    which_bin = shutil.which(settings.FFPROBE_PATH)
    if which_bin:
        try:
            return str(Path(which_bin).resolve())
        except Exception:
            return which_bin

    # Common Windows installation paths (Winget, Scoop, Program Files)
    possible_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffprobe.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "ffmpeg" / "bin" / "ffprobe.exe",
        Path("C:/ffmpeg/bin/ffprobe.exe"),
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "shims" / "ffprobe.exe",
    ]
    for p in possible_paths:
        if p.exists():
            try:
                return str(p.resolve())
            except Exception:
                return str(p)
    return settings.FFPROBE_PATH
