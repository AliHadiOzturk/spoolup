"""CRUD operations for the video management system."""

from typing import Optional, List, Any, Dict
from datetime import datetime

from sqlalchemy.orm import Session

from .models import (
    User,
    Printer,
    Video,
    ProcessedVideo,
    Upload,
    VideoAnalytics,
    PlatformSettings,
)


# --- User CRUD ---

def create_user(
    db: Session,
    username: str,
    password_hash: str,
    email: Optional[str] = None,
) -> User:
    user = User(
        username=username,
        password_hash=password_hash,
        email=email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    return db.query(User).offset(skip).limit(limit).all()


def update_user(
    db: Session,
    user_id: int,
    **kwargs: Any,
) -> Optional[User]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    for key, value in kwargs.items():
        if hasattr(user, key):
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True


# --- Printer CRUD ---

def create_printer(
    db: Session,
    name: str,
    moonraker_url: str,
    api_key: Optional[str] = None,
) -> Printer:
    printer = Printer(
        name=name,
        moonraker_url=moonraker_url,
        api_key=api_key,
    )
    db.add(printer)
    db.commit()
    db.refresh(printer)
    return printer


def get_printer_by_id(db: Session, printer_id: int) -> Optional[Printer]:
    return db.query(Printer).filter(Printer.id == printer_id).first()


def get_printers(db: Session, skip: int = 0, limit: int = 100) -> List[Printer]:
    return db.query(Printer).offset(skip).limit(limit).all()


def update_printer(
    db: Session,
    printer_id: int,
    **kwargs: Any,
) -> Optional[Printer]:
    printer = get_printer_by_id(db, printer_id)
    if not printer:
        return None
    for key, value in kwargs.items():
        if hasattr(printer, key):
            setattr(printer, key, value)
    db.commit()
    db.refresh(printer)
    return printer


def delete_printer(db: Session, printer_id: int) -> bool:
    printer = get_printer_by_id(db, printer_id)
    if not printer:
        return False
    db.delete(printer)
    db.commit()
    return True


# --- Video CRUD ---

def create_video(
    db: Session,
    printer_id: int,
    filename: str,
    original_path: str,
    size_bytes: int,
    duration_seconds: float,
    width: int,
    height: int,
    fps: float,
    moonraker_metadata_json: Optional[Dict[str, Any]] = None,
) -> Video:
    video = Video(
        printer_id=printer_id,
        filename=filename,
        original_path=original_path,
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        fps=fps,
        moonraker_metadata_json=moonraker_metadata_json,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def get_video_by_id(db: Session, video_id: int) -> Optional[Video]:
    return db.query(Video).filter(Video.id == video_id).first()


def get_videos_by_printer(
    db: Session, printer_id: int, skip: int = 0, limit: int = 100
) -> List[Video]:
    return (
        db.query(Video)
        .filter(Video.printer_id == printer_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_videos(db: Session, skip: int = 0, limit: int = 100) -> List[Video]:
    return db.query(Video).offset(skip).limit(limit).all()


def update_video(
    db: Session,
    video_id: int,
    **kwargs: Any,
) -> Optional[Video]:
    video = get_video_by_id(db, video_id)
    if not video:
        return None
    for key, value in kwargs.items():
        if hasattr(video, key):
            setattr(video, key, value)
    db.commit()
    db.refresh(video)
    return video


def delete_video(db: Session, video_id: int) -> bool:
    video = get_video_by_id(db, video_id)
    if not video:
        return False
    db.delete(video)
    db.commit()
    return True


# --- ProcessedVideo CRUD ---

def create_processed_video(
    db: Session,
    video_id: int,
    processed_path: str,
    width: int,
    height: int,
    duration_seconds: float,
    format: str,
    status: str = "pending",
) -> ProcessedVideo:
    processed = ProcessedVideo(
        video_id=video_id,
        processed_path=processed_path,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        format=format,
        status=status,
    )
    db.add(processed)
    db.commit()
    db.refresh(processed)
    return processed


def get_processed_video_by_id(
    db: Session, processed_video_id: int
) -> Optional[ProcessedVideo]:
    return (
        db.query(ProcessedVideo)
        .filter(ProcessedVideo.id == processed_video_id)
        .first()
    )


def get_processed_videos_by_video(
    db: Session, video_id: int, skip: int = 0, limit: int = 100
) -> List[ProcessedVideo]:
    return (
        db.query(ProcessedVideo)
        .filter(ProcessedVideo.video_id == video_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_processed_video(
    db: Session,
    processed_video_id: int,
    **kwargs: Any,
) -> Optional[ProcessedVideo]:
    processed = get_processed_video_by_id(db, processed_video_id)
    if not processed:
        return None
    for key, value in kwargs.items():
        if hasattr(processed, key):
            setattr(processed, key, value)
    db.commit()
    db.refresh(processed)
    return processed


def delete_processed_video(db: Session, processed_video_id: int) -> bool:
    processed = get_processed_video_by_id(db, processed_video_id)
    if not processed:
        return False
    db.delete(processed)
    db.commit()
    return True


# --- Upload CRUD ---

def create_upload(
    db: Session,
    processed_video_id: int,
    platform: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
    status: str = "pending",
) -> Upload:
    upload = Upload(
        processed_video_id=processed_video_id,
        platform=platform,
        title=title,
        description=description,
        tags=tags,
        status=status,
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


def get_upload_by_id(db: Session, upload_id: int) -> Optional[Upload]:
    return db.query(Upload).filter(Upload.id == upload_id).first()


def get_uploads_by_processed_video(
    db: Session, processed_video_id: int, skip: int = 0, limit: int = 100
) -> List[Upload]:
    return (
        db.query(Upload)
        .filter(Upload.processed_video_id == processed_video_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_upload(
    db: Session,
    upload_id: int,
    **kwargs: Any,
) -> Optional[Upload]:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return None
    for key, value in kwargs.items():
        if hasattr(upload, key):
            setattr(upload, key, value)
    db.commit()
    db.refresh(upload)
    return upload


def delete_upload(db: Session, upload_id: int) -> bool:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return False
    db.delete(upload)
    db.commit()
    return True


# --- VideoAnalytics CRUD ---

def create_video_analytics(
    db: Session,
    upload_id: int,
    views: int = 0,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
) -> VideoAnalytics:
    analytics = VideoAnalytics(
        upload_id=upload_id,
        views=views,
        likes=likes,
        comments=comments,
        shares=shares,
    )
    db.add(analytics)
    db.commit()
    db.refresh(analytics)
    return analytics


def get_analytics_by_id(db: Session, analytics_id: int) -> Optional[VideoAnalytics]:
    return db.query(VideoAnalytics).filter(VideoAnalytics.id == analytics_id).first()


def get_analytics_by_upload(
    db: Session, upload_id: int, skip: int = 0, limit: int = 100
) -> List[VideoAnalytics]:
    return (
        db.query(VideoAnalytics)
        .filter(VideoAnalytics.upload_id == upload_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_video_analytics(
    db: Session,
    analytics_id: int,
    **kwargs: Any,
) -> Optional[VideoAnalytics]:
    analytics = get_analytics_by_id(db, analytics_id)
    if not analytics:
        return None
    for key, value in kwargs.items():
        if hasattr(analytics, key):
            setattr(analytics, key, value)
    db.commit()
    db.refresh(analytics)
    return analytics


def delete_video_analytics(db: Session, analytics_id: int) -> bool:
    analytics = get_analytics_by_id(db, analytics_id)
    if not analytics:
        return False
    db.delete(analytics)
    db.commit()
    return True


# --- PlatformSettings CRUD ---

def create_platform_settings(
    db: Session,
    platform: str,
    settings_json: Dict[str, Any],
) -> PlatformSettings:
    settings = PlatformSettings(
        platform=platform,
        settings_json=settings_json,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def get_platform_settings_by_id(
    db: Session, settings_id: int
) -> Optional[PlatformSettings]:
    return (
        db.query(PlatformSettings)
        .filter(PlatformSettings.id == settings_id)
        .first()
    )


def get_platform_settings_by_platform(
    db: Session, platform: str
) -> Optional[PlatformSettings]:
    return (
        db.query(PlatformSettings)
        .filter(PlatformSettings.platform == platform)
        .first()
    )


def get_all_platform_settings(
    db: Session, skip: int = 0, limit: int = 100
) -> List[PlatformSettings]:
    return db.query(PlatformSettings).offset(skip).limit(limit).all()


def update_platform_settings(
    db: Session,
    settings_id: int,
    **kwargs: Any,
) -> Optional[PlatformSettings]:
    settings = get_platform_settings_by_id(db, settings_id)
    if not settings:
        return None
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


def delete_platform_settings(db: Session, settings_id: int) -> bool:
    settings = get_platform_settings_by_id(db, settings_id)
    if not settings:
        return False
    db.delete(settings)
    db.commit()
    return True
