import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
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

# --- Clips Management APIs ---
@app.get("/api/clips")
def get_clips(db: Session = Depends(get_db)):
    return db.query(ClipTask).order_by(ClipTask.id.desc()).limit(50).all()

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
    return {
        "youtube": settings.YOUTUBE_TOKEN_FILE.exists(),
        "tiktok": browser_uploader.is_logged_in("tiktok"),
        "instagram": browser_uploader.is_logged_in("instagram")
    }

@app.post("/api/socials/login/{platform}")
async def trigger_social_login(platform: str, background_tasks: BackgroundTasks):
    if platform not in ["tiktok", "instagram"]:
        raise HTTPException(status_code=400, detail="Invalid platform")
    from app.publishers.browser_uploader import browser_uploader
    background_tasks.add_task(browser_uploader.launch_login_session, platform)
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
