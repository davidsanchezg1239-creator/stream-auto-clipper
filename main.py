import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings, find_ffmpeg_binary
from app.database import engine, get_db, Base
from app.models import Channel, ClipTask, CompilationTask, PublishLog
from app.pipeline import ClipperPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main_server")

# Global pipeline & scheduler
pipeline = ClipperPipeline()
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure tables exist
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)
    
    # Check FFmpeg
    ffmpeg_bin = find_ffmpeg_binary()
    logger.info(f"FFmpeg detected at: {ffmpeg_bin}")

    # Start periodic background monitor
    scheduler.add_job(
        pipeline.scan_all_channels,
        "interval",
        seconds=settings.CHECK_INTERVAL_SECONDS,
        id="channel_scanner",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started: scanning channels every {settings.CHECK_INTERVAL_SECONDS} seconds.")
    
    yield
    
    # Shutdown
    scheduler.shutdown()
    logger.info("Scheduler shutdown.")

app = FastAPI(title="Stream Auto Clipper API", version="1.0.0", lifespan=lifespan)

# Mount storage directory for static video serving
app.mount("/storage", StaticFiles(directory=str(settings.DOWNLOADS_DIR.parent)), name="storage")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "app" / "templates"))

# --- Pydantic Schemas ---
class ChannelCreate(BaseModel):
    platform: str
    channel_name: str

class AutoPilotPayload(BaseModel):
    auto_publish: bool
    min_score: Optional[float] = 8.0

class CustomClipCreate(BaseModel):
    clip_url: str
    channel_id: Optional[int] = None
    layout: Optional[str] = "blur"  # "blur", "center", or "split"

class CompilationCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    clip_ids: List[int]

# --- Frontend Dashboard Route ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- Channel Management APIs ---
@app.get("/api/channels")
def get_channels(db: Session = Depends(get_db)):
    return db.query(Channel).order_by(Channel.created_at.desc()).all()

@app.post("/api/channels")
async def add_channel(payload: ChannelCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    name = payload.channel_name.strip().lower()
    existing = db.query(Channel).filter(Channel.channel_name == name, Channel.platform == payload.platform).first()
    if existing:
        raise HTTPException(status_code=400, detail="Channel already exists")

    ch = Channel(
        platform=payload.platform.lower(),
        channel_name=name,
        display_name=name
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    # Immediately check this channel in the background
    background_tasks.add_task(pipeline.check_channel, ch.id)
    return ch

@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(ch)
    db.commit()
    return {"message": "Channel deleted"}

@app.post("/api/scan")
async def trigger_scan(background_tasks: BackgroundTasks):
    background_tasks.add_task(pipeline.scan_all_channels)
    return {"message": "Scan triggered"}

# --- GTA 6 Radar & Pre-seeded Streamers ---
GTA6_PRESET_STREAMERS = [
    {"platform": "twitch", "channel_name": "auronplay", "display_name": "AuronPlay"},
    {"platform": "twitch", "channel_name": "ibai", "display_name": "Ibai Llanos"},
    {"platform": "twitch", "channel_name": "illojuan", "display_name": "IlloJuan"},
    {"platform": "twitch", "channel_name": "rubius", "display_name": "Rubius"},
    {"platform": "twitch", "channel_name": "elxokas", "display_name": "ElXokas"},
    {"platform": "twitch", "channel_name": "thegrefg", "display_name": "TheGrefg"},
    {"platform": "twitch", "channel_name": "spreen", "display_name": "Spreen"},
    {"platform": "twitch", "channel_name": "rivers_gg", "display_name": "Rivers GG"},
    {"platform": "twitch", "channel_name": "juansguarnizo", "display_name": "JuanSGuarnizo"},
    {"platform": "twitch", "channel_name": "alexby11", "display_name": "Alexby11"},
    {"platform": "kick", "channel_name": "westcol", "display_name": "WestCOL"},
    {"platform": "kick", "channel_name": "xqc", "display_name": "xQc"},
    {"platform": "kick", "channel_name": "adinross", "display_name": "Adin Ross"},
]

@app.post("/api/channels/seed-gta6")
async def seed_gta6_channels(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Pre-seeds top-tier Spanish and global streamers for GTA 6 launch day."""
    added = []
    for s in GTA6_PRESET_STREAMERS:
        existing = db.query(Channel).filter(
            Channel.channel_name == s["channel_name"],
            Channel.platform == s["platform"]
        ).first()
        if not existing:
            ch = Channel(
                platform=s["platform"],
                channel_name=s["channel_name"],
                display_name=s["display_name"]
            )
            db.add(ch)
            added.append(s["channel_name"])
    db.commit()
    background_tasks.add_task(pipeline.scan_all_channels)
    return {"message": f"Se agregaron {len(added)} streamers para el estreno de GTA 6.", "added": added}

@app.get("/api/settings/autopilot")
def get_autopilot_settings():
    return {
        "auto_publish": settings.AUTO_PUBLISH_VIRAL,
        "min_score": settings.AUTO_PUBLISH_MIN_SCORE,
        "gta6_turbo": settings.GTA6_TURBO_ENABLED
    }

@app.post("/api/settings/autopilot")
def update_autopilot_settings(payload: AutoPilotPayload):
    settings.AUTO_PUBLISH_VIRAL = payload.auto_publish
    if payload.min_score is not None:
        settings.AUTO_PUBLISH_MIN_SCORE = payload.min_score
    logger.info(f"Auto-Pilot setting changed: enabled={settings.AUTO_PUBLISH_VIRAL}, min_score={settings.AUTO_PUBLISH_MIN_SCORE}")
    return {
        "message": "Configuración de Auto-Pilot actualizada",
        "auto_publish": settings.AUTO_PUBLISH_VIRAL,
        "min_score": settings.AUTO_PUBLISH_MIN_SCORE
    }

@app.get("/api/radar/status")
def get_radar_status(db: Session = Depends(get_db)):
    channels = db.query(Channel).all()
    gta6_live = [
        c.channel_name for c in channels
        if c.is_live and pipeline.analyzer.is_gta6_content(c.stream_game or "", c.stream_title or "", "")
    ]
    return {
        "turbo_enabled": settings.GTA6_TURBO_ENABLED,
        "gta6_live": gta6_live,
        "is_active": len(gta6_live) > 0,
        "total_monitored": len(channels)
    }

# --- Clips Management APIs ---
@app.get("/api/clips")
def get_clips(db: Session = Depends(get_db)):
    clips = db.query(ClipTask).order_by(ClipTask.id.desc()).limit(50).all()
    results = []
    for c in clips:
        ch = c.channel
        logs = c.publish_logs or []
        logs_summary = [
            {"platform": l.target_platform, "status": l.status, "url": l.external_url}
            for l in logs
        ]
        results.append({
            "id": c.id,
            "channel_id": c.channel_id,
            "streamer_name": (ch.display_name or ch.channel_name) if ch else "Personalizado",
            "streamer_username": ch.channel_name if ch else "",
            "stream_game": (ch.stream_game if ch else "") or "",
            "source_platform": c.source_platform or (ch.platform if ch else "twitch"),
            "source_url": c.source_url,
            "original_title": c.original_title or f"Clip #{c.id}",
            "duration_seconds": c.duration_seconds or 0.0,
            "transcript_text": c.transcript_text or "",
            "ai_score": c.ai_score or 0.0,
            "ai_category": c.ai_category or "general",
            "ai_title": c.ai_title or c.original_title or f"Clip #{c.id}",
            "ai_description": c.ai_description or "",
            "ai_hashtags": c.ai_hashtags or "",
            "processed_path_vertical": c.processed_path_vertical,
            "status": c.status,
            "error_message": c.error_message,
            "created_at": c.created_at.strftime("%d/%m %H:%M") if c.created_at else "",
            "publish_logs": logs_summary
        })
    return results

@app.post("/api/clips/custom")
async def add_custom_clip(payload: CustomClipCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    task = ClipTask(
        channel_id=payload.channel_id,
        source_platform="custom",
        source_url=payload.clip_url,
        status="PENDING"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Launch processing pipeline asynchronously
    layout = payload.layout or "blur"
    background_tasks.add_task(pipeline.process_clip, task.id, layout=layout)
    return {"message": "Clip queued for processing", "task_id": task.id}

@app.post("/api/clips/{clip_id}/process")
async def reprocess_clip(clip_id: int, background_tasks: BackgroundTasks, layout: str = "blur", db: Session = Depends(get_db)):
    task = db.query(ClipTask).filter(ClipTask.id == clip_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Clip not found")
    background_tasks.add_task(pipeline.process_clip, task.id, layout=layout)
    return {"message": f"Reprocessing initiated for clip #{clip_id} with layout {layout}"}

@app.post("/api/clips/{clip_id}/publish")
async def publish_clip(clip_id: int):
    res = await pipeline.auto_publish_clip(clip_id)
    return res

@app.post("/api/clips/{clip_id}/publish/{platform}")
async def publish_clip_single(clip_id: int, platform: str, db: Session = Depends(get_db)):
    """Publishes a clip specifically to youtube, tiktok, or instagram."""
    task = db.query(ClipTask).filter(ClipTask.id == clip_id).first()
    if not task or not task.processed_path_vertical:
        raise HTTPException(status_code=400, detail="Clip not ready or not found")

    title = task.ai_title or task.original_title or "Momento Épico"
    desc = f"{task.ai_description or ''}\n\n{task.ai_hashtags or ''}".strip()
    file_path = task.processed_path_vertical

    from app.publishers.browser_uploader import browser_uploader
    from app.models import PublishLog

    res = {}
    if platform == "youtube":
        res = await pipeline.yt_publisher.upload_video(file_path=file_path, title=title, description=desc, is_short=True)
        log = PublishLog(clip_id=task.id, target_platform="youtube_shorts", status="SUCCESS" if res.get("success") else "FAILED", external_url=res.get("url"), error_detail=res.get("error"))
        db.add(log)
    elif platform == "tiktok":
        res = await browser_uploader.upload_tiktok_reel(video_path=file_path, caption=f"{title}\n{task.ai_hashtags or ''}")
        log = PublishLog(clip_id=task.id, target_platform="tiktok", status="SUCCESS" if res.get("success") else "FAILED", error_detail=res.get("error"))
        db.add(log)
    elif platform == "instagram":
        res = await browser_uploader.upload_instagram_reel(video_path=file_path, caption=f"{title}\n\n{desc}")
        log = PublishLog(clip_id=task.id, target_platform="instagram_reels", status="SUCCESS" if res.get("success") else "FAILED", error_detail=res.get("error"))
        db.add(log)
    else:
        raise HTTPException(status_code=400, detail="Plataforma inválida. Usa: youtube, tiktok o instagram")

    if res.get("success"):
        task.status = "PUBLISHED"
    db.commit()
    return res

@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: int, db: Session = Depends(get_db)):
    """Downloads the processed 9:16 vertical MP4 video directly."""
    task = db.query(ClipTask).filter(ClipTask.id == clip_id).first()
    if not task or not task.processed_path_vertical:
        raise HTTPException(status_code=404, detail="Clip vertical aún no generado o no encontrado")
    file_path = Path(task.processed_path_vertical)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado en disco")
    
    clean_title = "".join(c for c in (task.ai_title or task.original_title or f"clip_{task.id}") if c.isalnum() or c in (" ", "-", "_")).strip()
    safe_name = f"{clean_title[:60].strip() or f'clip_{task.id}'}.mp4"
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="video/mp4"
    )

@app.post("/api/clips/{clip_id}/toggle-status")
def toggle_clip_status(clip_id: int, db: Session = Depends(get_db)):
    """Toggles clip status between PUBLISHED and READY_TO_PUBLISH for manual tracking."""
    task = db.query(ClipTask).filter(ClipTask.id == clip_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    task.status = "PUBLISHED" if task.status != "PUBLISHED" else "READY_TO_PUBLISH"
    db.commit()
    return {"id": task.id, "status": task.status}

# --- Long-form Compilation API ---
@app.post("/api/compilations")
async def create_compilation(payload: CompilationCreate):
    res = await pipeline.compile_long_form_youtube(
        clip_ids=payload.clip_ids,
        title=payload.title,
        description=payload.description
    )
    return res

@app.get("/api/compilations")
def get_compilations(db: Session = Depends(get_db)):
    return db.query(CompilationTask).order_by(CompilationTask.id.desc()).all()

@app.post("/api/compilations/{compilation_id}/publish")
async def publish_compilation(compilation_id: int):
    return await pipeline.publish_compilation(compilation_id)
# --- Social Accounts & Connections APIs ---
@app.get("/api/socials/status")
def get_socials_status():
    from app.publishers.browser_uploader import browser_uploader
    yt_connected = False
    if settings.YOUTUBE_TOKEN_FILE.exists():
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(settings.YOUTUBE_TOKEN_FILE))
            yt_connected = bool(creds and not creds.expired)
        except Exception:
            yt_connected = False
    return {
        "youtube": yt_connected,
        "tiktok": browser_uploader.is_logged_in("tiktok"),
        "instagram": browser_uploader.is_logged_in("instagram")
    }

@app.post("/api/socials/login/{platform}")
async def trigger_social_login(platform: str, background_tasks: BackgroundTasks):
    if platform == "youtube":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pipeline.yt_publisher.start_oauth_flow)
    if platform not in ["tiktok", "instagram"]:
        raise HTTPException(status_code=400, detail="Invalid platform")
    from app.publishers.browser_uploader import browser_uploader
    background_tasks.add_task(browser_uploader.launch_login_session, platform)
    return {"message": f"Iniciando navegador para autenticar en {platform}..."}
class CookiePayload(BaseModel):
    platform: str
    session_id: str
    user_id: Optional[str] = None

@app.post("/api/socials/cookies")
def set_social_cookies(payload: CookiePayload):
    from app.publishers.browser_uploader import browser_uploader
    browser_uploader.set_session_cookie(payload.platform, payload.session_id, payload.user_id)
    return {"message": f"Cookies guardadas con éxito para {payload.platform}", "connected": True}

# --- Twitch EventSub Webhook Receiver ---
@app.post("/webhooks/twitch")
async def twitch_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Handles official Twitch EventSub webhooks (stream.online / stream.offline)."""
    headers = request.headers
    message_type = headers.get("Twitch-Eventsub-Message-Type")

    # Respond to Twitch webhook challenge
    if message_type == "webhook_callback_verification":
        body = await request.json()
        return HTMLResponse(content=body.get("challenge"), status_code=200)

    if message_type == "notification":
        data = await request.json()
        event = data.get("event", {})
        broadcaster_name = event.get("broadcaster_user_login")
        if broadcaster_name:
            ch = db.query(Channel).filter(Channel.channel_name == broadcaster_name).first()
            if ch:
                subscription_type = data.get("subscription", {}).get("type")
                if subscription_type == "stream.online":
                    ch.is_live = True
                    db.commit()
                    background_tasks.add_task(pipeline.check_channel, ch.id)
                elif subscription_type == "stream.offline":
                    ch.is_live = False
                    db.commit()

        return JSONResponse({"status": "received"})

    return JSONResponse({"status": "ignored"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
