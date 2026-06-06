"""SQLAlchemy models for the video management system."""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Boolean,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    moonraker_url: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    videos: Mapped[List["Video"]] = relationship("Video", back_populates="printer")
    zip_archives: Mapped[List["ZipArchive"]] = relationship("ZipArchive", back_populates="printer")


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    printer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("printers.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    moonraker_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # User-defined metadata (set before processing)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Processing options
    processing_options: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status tracking
    metadata_status: Mapped[str] = mapped_column(String(20), default="pending")

    # Thumbnail path (from Moonraker - same name with image extension)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    printer: Mapped["Printer"] = relationship("Printer", back_populates="videos")
    processed_videos: Mapped[List["ProcessedVideo"]] = relationship(
        "ProcessedVideo", back_populates="video"
    )


class ProcessedVideo(Base):
    __tablename__ = "processed_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id"), nullable=False
    )
    processed_path: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    video: Mapped["Video"] = relationship("Video", back_populates="processed_videos")
    uploads: Mapped[List["Upload"]] = relationship("Upload", back_populates="processed_video")
    text_overlays: Mapped[List["TextOverlay"]] = relationship(
        "TextOverlay", back_populates="processed_video"
    )
    video_audios: Mapped[List["VideoAudio"]] = relationship(
        "VideoAudio", back_populates="processed_video"
    )


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    processed_video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("processed_videos.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_video_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    upload_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Enhanced status tracking
    upload_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platform_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    processed_video: Mapped["ProcessedVideo"] = relationship(
        "ProcessedVideo", back_populates="uploads"
    )
    analytics: Mapped[List["VideoAnalytics"]] = relationship(
        "VideoAnalytics", back_populates="upload"
    )


class VideoAnalytics(Base):
    __tablename__ = "video_analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id"), nullable=False
    )
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    upload: Mapped["Upload"] = relationship("Upload", back_populates="analytics")


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# =============================================================================
# Post-Processing Tables
# =============================================================================

class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    video_audios: Mapped[List["VideoAudio"]] = relationship(
        "VideoAudio", back_populates="audio_track"
    )


class TextOverlay(Base):
    __tablename__ = "text_overlays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    processed_video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("processed_videos.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
    font_size: Mapped[int] = mapped_column(Integer, default=36)
    font_color: Mapped[str] = mapped_column(String(20), default="white")
    bg_color: Mapped[str] = mapped_column(String(20), default="black@0.5")
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    processed_video: Mapped["ProcessedVideo"] = relationship(
        "ProcessedVideo", back_populates="text_overlays"
    )


class VideoAudio(Base):
    __tablename__ = "video_audio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    processed_video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("processed_videos.id"), nullable=False
    )
    audio_track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("audio_tracks.id"), nullable=False
    )
    volume: Mapped[float] = mapped_column(Float, default=0.5)
    fade_in: Mapped[float] = mapped_column(Float, default=2.0)
    fade_out: Mapped[float] = mapped_column(Float, default=2.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    processed_video: Mapped["ProcessedVideo"] = relationship(
        "ProcessedVideo", back_populates="video_audios"
    )
    audio_track: Mapped["AudioTrack"] = relationship(
        "AudioTrack", back_populates="video_audios"
    )


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("uploads.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ZipArchive(Base):
    __tablename__ = "zip_archives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    printer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("printers.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    moonraker_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    printer: Mapped["Printer"] = relationship("Printer", back_populates="zip_archives")
