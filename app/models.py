import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False)  # "twitch" or "kick"
    channel_name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    is_live = Column(Boolean, default=False)
    stream_title = Column(String(300), nullable=True)
    stream_game = Column(String(200), nullable=True)
    auto_clip_enabled = Column(Boolean, default=True)
    last_checked_at = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    clips = relationship("ClipTask", back_populates="channel", cascade="all, delete-orphan")


class ClipTask(Base):
    __tablename__ = "clip_tasks"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)
    source_platform = Column(String(50), default="twitch")  # twitch, kick, custom
    source_url = Column(String(500), nullable=False)
    original_title = Column(String(300), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    
    # Local raw file path
    download_path = Column(String(500), nullable=True)
    
    # AI Transcribed & Analyzed Data
    transcript_text = Column(Text, nullable=True)
    transcript_segments_json = Column(Text, nullable=True)  # JSON timestamps for subtitles
    ai_score = Column(Float, default=0.0)  # 0 to 10 viral score
    ai_category = Column(String(50), nullable=True)  # "funny", "rage", "clutch", "story", "fail"
    ai_title = Column(String(300), nullable=True)
    ai_description = Column(Text, nullable=True)
    ai_hashtags = Column(String(300), nullable=True)
    
    # Edited Video Paths
    processed_path_vertical = Column(String(500), nullable=True)
    subtitle_ass_path = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    
    # Pipeline Processing Status:
    # PENDING -> DOWNLOADING -> TRANSCRIBING -> ANALYZING -> EDITING -> READY_TO_PUBLISH -> PUBLISHED -> FAILED
    status = Column(String(50), default="PENDING", index=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    channel = relationship("Channel", back_populates="clips")
    publish_logs = relationship("PublishLog", back_populates="clip", cascade="all, delete-orphan")


class CompilationTask(Base):
    __tablename__ = "compilation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)
    clip_ids_json = Column(Text, nullable=False)  # JSON list of clip IDs included
    output_path = Column(String(500), nullable=True)
    duration_seconds = Column(Float, default=0.0)
    
    # DRAFT -> RENDERING -> READY -> PUBLISHED -> FAILED
    status = Column(String(50), default="DRAFT", index=True)
    youtube_video_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    publish_logs = relationship("PublishLog", back_populates="compilation", cascade="all, delete-orphan")


class PublishLog(Base):
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, index=True)
    clip_id = Column(Integer, ForeignKey("clip_tasks.id"), nullable=True)
    compilation_id = Column(Integer, ForeignKey("compilation_tasks.id"), nullable=True)
    target_platform = Column(String(50), nullable=False)  # "youtube_shorts", "youtube_long", "tiktok", "instagram_reels"
    
    status = Column(String(50), default="PENDING")  # "SUCCESS", "FAILED"
    external_post_id = Column(String(200), nullable=True)
    external_url = Column(String(500), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    clip = relationship("ClipTask", back_populates="publish_logs")
    compilation = relationship("CompilationTask", back_populates="publish_logs")
