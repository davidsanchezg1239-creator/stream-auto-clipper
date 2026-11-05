import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import SessionLocal
from app.models import Channel, ClipTask, CompilationTask, PublishLog
from app.monitors.twitch_monitor import TwitchMonitor
from app.monitors.kick_monitor import KickMonitor
from app.capture.stream_recorder import StreamRecorder
from app.ai.transcriber import AudioTranscriber
from app.ai.analyzer import ClipAnalyzer
from app.ai.face_tracker import FaceTracker
from app.editor.subtitle_generator import SubtitleGenerator
from app.editor.video_processor import VideoProcessor
from app.editor.compiler import VideoCompiler
from app.publishers.youtube import YouTubePublisher
from app.publishers.social_dispatcher import SocialDispatcher

logger = logging.getLogger("pipeline_orchestrator")

class ClipperPipeline:
    def __init__(self):
        self.twitch_monitor = TwitchMonitor()
        self.kick_monitor = KickMonitor()
        self.recorder = StreamRecorder()
        self.transcriber = AudioTranscriber()
        self.analyzer = ClipAnalyzer()
        self.face_tracker = FaceTracker()
        self.sub_generator = SubtitleGenerator()
        self.video_processor = VideoProcessor()
        self.compiler = VideoCompiler()
        self.yt_publisher = YouTubePublisher()
        self.social_dispatcher = SocialDispatcher()

    async def scan_all_channels(self) -> Dict[str, Any]:
        """Scans all registered channels to check live status and harvest clips."""
        db: Session = SessionLocal()
        gta6_active = []
        try:
            channels = db.query(Channel).all()
            for ch in channels:
                try:
                    res = await self.check_channel(ch.id)
                    if res and res.get("is_gta6") and res.get("is_live"):
                        gta6_active.append(ch.channel_name)
                except Exception as e:
                    logger.error(f"Error checking channel {ch.channel_name}: {e}")
            return {"scanned": len(channels), "gta6_active": gta6_active}
        finally:
            db.close()

    async def check_channel(self, channel_id: int) -> Dict[str, Any]:
        """Checks status of a single channel and imports new clips if live."""
        db: Session = SessionLocal()
        is_gta6 = False
        is_live = False
        try:
            channel = db.query(Channel).filter(Channel.id == channel_id).first()
            if not channel:
                return {"is_live": False, "is_gta6": False}

            platform = channel.platform.lower()
            status_data = {}
            clips_data = []

            if platform == "twitch":
                status_data = await self.twitch_monitor.get_stream_status(channel.channel_name)
                is_live = status_data.get("is_live", False)
                channel.is_live = is_live
                if is_live:
                    channel.stream_title = status_data.get("title")
                    channel.stream_game = status_data.get("game_name")
                    is_gta6 = self.analyzer.is_gta6_content(
                        channel.stream_game or "", channel.stream_title or "", ""
                    )
                    user_id = status_data.get("user_id")
                    if user_id and channel.auto_clip_enabled:
                        fetch_limit = 10 if (is_gta6 and settings.GTA6_TURBO_ENABLED) else 3
                        if is_gta6:
                            logger.info(f"🚨 [GTA 6 RADAR] {channel.channel_name} is LIVE on GTA VI ({channel.stream_title})! Fetching {fetch_limit} clips.")
                        clips_data = await self.twitch_monitor.fetch_recent_clips(
                            user_id, started_at=status_data.get("started_at"), limit=fetch_limit
                        )
            elif platform == "kick":
                status_data = await self.kick_monitor.get_stream_status(channel.channel_name)
                is_live = status_data.get("is_live", False)
                channel.is_live = is_live
                if is_live:
                    channel.stream_title = status_data.get("title")
                    channel.stream_game = status_data.get("game_name")
                    is_gta6 = self.analyzer.is_gta6_content(
                        channel.stream_game or "", channel.stream_title or "", ""
                    )
                    if channel.auto_clip_enabled:
                        fetch_limit = 10 if (is_gta6 and settings.GTA6_TURBO_ENABLED) else 3
                        if is_gta6:
                            logger.info(f"🚨 [GTA 6 RADAR] Kick {channel.channel_name} is LIVE on GTA VI! Fetching {fetch_limit} clips.")
                        clips_data = await self.kick_monitor.fetch_recent_clips(channel.channel_name, limit=fetch_limit)

            db.commit()

            # Process discovered clips
            for clip_item in clips_data:
                clip_url = clip_item.get("url")
                if not clip_url:
                    continue

                # Check if clip is already registered
                existing = db.query(ClipTask).filter(ClipTask.source_url == clip_url).first()
                if not existing:
                    task = ClipTask(
                        channel_id=channel.id,
                        source_platform=platform,
                        source_url=clip_url,
                        original_title=clip_item.get("title", ""),
                        duration_seconds=clip_item.get("duration", 30.0),
                        status="PENDING"
                    )
                    db.add(task)
                    db.commit()
                    db.refresh(task)
                    logger.info(f"Discovered new clip: {task.original_title} ({clip_url})")

                    # Process the new clip in background
                    await self.process_clip(task.id)

            return {"is_live": is_live, "is_gta6": is_gta6}

        finally:
            db.close()

    async def process_clip(self, clip_task_id: int, layout: str = "auto"):
        """
        Executes full pipeline:
        Download -> Transcribe -> Gemini Analysis -> Face Tracking -> Subtitles -> Vertical Render
        """
        db: Session = SessionLocal()
        try:
            task = db.query(ClipTask).filter(ClipTask.id == clip_task_id).first()
            if not task:
                return

            logger.info(f"Starting processing for Clip #{task.id}: {task.original_title or task.source_url}")

            # 1. Download
            task.status = "DOWNLOADING"
            db.commit()
            dl_res = await self.recorder.download_clip(task.source_url, custom_filename=f"clip_{task.id}")
            if not dl_res.get("success"):
                task.status = "FAILED"
                task.error_message = f"Download failed: {dl_res.get('error')}"
                db.commit()
                return

            task.download_path = dl_res.get("file_path")
            task.duration_seconds = dl_res.get("duration", 30.0)
            if not task.original_title:
                task.original_title = dl_res.get("title", "")
            db.commit()

            # 2. Transcribe Audio
            task.status = "TRANSCRIBING"
            db.commit()
            trans_res = await self.transcriber.transcribe(task.download_path)
            task.transcript_text = trans_res.get("full_text", "")
            task.transcript_segments_json = json.dumps(trans_res.get("segments", []))
            db.commit()

            # 3. AI Analysis & Hook Generation
            task.status = "ANALYZING"
            db.commit()
            channel_name = task.channel.channel_name if task.channel else ""
            game_name = task.channel.stream_game if task.channel else ""
            analysis = await self.analyzer.analyze_clip(
                transcript=task.transcript_text,
                original_title=task.original_title,
                streamer_name=channel_name,
                game_name=game_name
            )
            task.ai_score = analysis.get("score", 7.0)
            task.ai_category = analysis.get("category", "funny")
            task.ai_title = analysis.get("title", task.original_title)
            task.ai_description = analysis.get("description", "")
            task.ai_hashtags = analysis.get("hashtags", "")
            db.commit()

            # 4. Face Detection & Subtitles
            task.status = "EDITING"
            db.commit()
            face_box = self.face_tracker.detect_streamer_webcam(task.download_path)
            
            # Check for GTA 6 content for specialized Vice City subtitles
            is_gta6 = self.analyzer.is_gta6_content(
                game_name=game_name,
                title=task.original_title or "",
                transcript=task.transcript_text or ""
            )
            sub_style = "vice_city" if is_gta6 else "default"
            if is_gta6:
                logger.info(f"🌴 [GTA 6 DETECTED] Applying Vice City neon subtitles for clip #{task.id}")

            # Generate Subtitles file (.ass)
            sub_file = str(Path(task.download_path).with_suffix(".ass"))
            segments = json.loads(task.transcript_segments_json or "[]")
            self.sub_generator.generate_ass(segments, sub_file, style=sub_style)
            task.subtitle_ass_path = sub_file

            # 5. Render 9:16 Vertical Short
            vert_filename = f"short_{task.id}.mp4"
            render_res = await self.video_processor.render_vertical_short(
                input_video=task.download_path,
                output_filename=vert_filename,
                face_box=face_box,
                subtitle_ass_path=sub_file,
                layout=layout
            )

            if render_res.get("success"):
                task.processed_path_vertical = render_res.get("output_path")
                task.status = "READY_TO_PUBLISH"
                task.error_message = None
                db.commit()
                logger.info(f"Clip #{task.id} successfully processed and ready at: {task.processed_path_vertical}")

                # 6. Auto-Pilot Mode: auto-publish if enabled and score qualifies
                if settings.AUTO_PUBLISH_VIRAL and (task.ai_score or 0.0) >= settings.AUTO_PUBLISH_MIN_SCORE:
                    logger.info(f"🚀 [AUTO-PILOT ACTIVATED] Clip #{task.id} scored {task.ai_score} >= {settings.AUTO_PUBLISH_MIN_SCORE}. Auto-publishing to YouTube, TikTok and Instagram...")
                    try:
                        await self.auto_publish_clip(task.id)
                    except Exception as pub_err:
                        logger.error(f"Auto-pilot publication error for clip #{task.id}: {pub_err}")
            else:
                task.status = "FAILED"
                task.error_message = f"Render failed: {render_res.get('error')}"
                db.commit()

        except Exception as e:
            logger.error(f"Error in pipeline for clip #{clip_task_id}: {e}")
            task.status = "FAILED"
            task.error_message = str(e)
            db.commit()
        finally:
            db.close()

    async def auto_publish_clip(self, clip_task_id: int) -> dict:
        """Publishes an edited vertical short to YouTube Shorts and social media."""
        db: Session = SessionLocal()
        try:
            task = db.query(ClipTask).filter(ClipTask.id == clip_task_id).first()
            if not task or not task.processed_path_vertical:
                return {"success": False, "error": "Clip not ready or not found"}

            title = task.ai_title or task.original_title or "Momento Épico"
            desc = f"{task.ai_description}\n\n{task.ai_hashtags}"

            # 1. YouTube Shorts
            yt_res = await self.yt_publisher.upload_video(
                file_path=task.processed_path_vertical,
                title=title,
                description=desc,
                is_short=True
            )
            log_yt = PublishLog(
                clip_id=task.id,
                target_platform="youtube_shorts",
                status="SUCCESS" if yt_res.get("success") else "FAILED",
                external_post_id=yt_res.get("video_id"),
                external_url=yt_res.get("url"),
                error_detail=yt_res.get("error")
            )
            db.add(log_yt)

            # 2. Instagram & TikTok Dispatcher
            soc_res = await self.social_dispatcher.publish_all(
                video_url_or_path=task.processed_path_vertical,
                caption=title,
                hashtags=task.ai_hashtags
            )

            task.status = "PUBLISHED"
            db.commit()
            return {"youtube": yt_res, "socials": soc_res}
        finally:
            db.close()

    async def compile_long_form_youtube(self, clip_ids: List[int], title: str, description: str = "") -> dict:
        """Takes top clips and compiles them into a 10-minute YouTube video."""
        db: Session = SessionLocal()
        try:
            clips = db.query(ClipTask).filter(ClipTask.id.in_(clip_ids)).all()
            video_paths = []
            for c in clips:
                if c.download_path:
                    p = Path(c.download_path)
                    if not p.is_absolute():
                        p = BASE_DIR / p
                    if p.exists():
                        video_paths.append(str(p))

            if not video_paths:
                return {"success": False, "error": "No valid raw clips found to compile"}

            comp_task = CompilationTask(
                title=title,
                description=description,
                clip_ids_json=json.dumps(clip_ids),
                status="RENDERING"
            )
            db.add(comp_task)
            db.commit()
            db.refresh(comp_task)

            res = await self.compiler.compile_long_form(
                video_paths=video_paths,
                output_filename=f"compilation_{comp_task.id}.mp4"
            )

            if res.get("success"):
                comp_task.output_path = res.get("output_path")
                comp_task.status = "READY"
                db.commit()
                return {"success": True, "compilation_id": comp_task.id, "path": comp_task.output_path}
            else:
                comp_task.status = "FAILED"
                comp_task.error_message = res.get("error")
                db.commit()
                return {"success": False, "error": res.get("error")}
        finally:
            db.close()

    async def publish_compilation(self, compilation_id: int) -> dict:
        """Publishes a 10-minute compilation video to YouTube as a regular long-form video."""
        db: Session = SessionLocal()
        try:
            task = db.query(CompilationTask).filter(CompilationTask.id == compilation_id).first()
            if not task or not task.output_path:
                return {"success": False, "error": "Compilation not found or not rendered"}

            yt_res = await self.yt_publisher.upload_video(
                file_path=task.output_path,
                title=task.title,
                description=task.description or "Recopilación de mejores momentos de streams.",
                is_short=False
            )
            if yt_res.get("success"):
                task.status = "PUBLISHED"
                task.youtube_video_id = yt_res.get("video_id")
            db.commit()
            return yt_res
        finally:
            db.close()
