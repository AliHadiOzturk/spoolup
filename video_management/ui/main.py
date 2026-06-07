"""FastAPI web interface for the video management system with Vue.js SPA."""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_current_admin_user,
    get_current_user,
    get_password_hash,
    oauth2_scheme,
)
from auth.dependencies import override_get_user
from auth.rate_limiter import rate_limit, SecurityHeadersMiddleware
from config import settings
from api.moonraker import MoonrakerClient
from database import get_db, SessionLocal
from database.crud import get_user_by_username
from database.models import (
    AudioTrack,
    Printer,
    ProcessedVideo,
    Upload,
    UploadJob,
    User,
    Video,
    VideoAnalytics,
    ZipArchive,
)

logger = logging.getLogger(__name__)


def _get_user_for_auth(username: str) -> Optional[User]:
    """Get user by username for auth dependencies (no db parameter)."""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


# Wire up the auth dependency to use our database
override_get_user(_get_user_for_auth)


# =============================================================================
# PKCE Storage for TikTok OAuth
# =============================================================================

# Temporary storage for PKCE code_verifier mapped to state parameter
# Entries expire after 10 minutes
_pkce_store: Dict[str, Dict[str, Any]] = {}


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge.

    Returns:
        Tuple of (code_verifier, code_challenge).
    """
    import hashlib
    import base64

    # Generate code_verifier: 43-128 chars random string
    code_verifier = base64.urlsafe_b64encode(
        os.urandom(32)
    ).decode("utf-8").rstrip("=")

    # Generate code_challenge: SHA256 hash of verifier, base64url encoded
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).decode("utf-8").rstrip("=")

    return code_verifier, code_challenge


def _store_pkce_verifier(state: str, verifier: str) -> None:
    """Store PKCE verifier mapped to state with expiration."""
    _pkce_store[state] = {
        "verifier": verifier,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }


def _get_pkce_verifier(state: str) -> Optional[str]:
    """Retrieve and remove PKCE verifier for given state."""
    entry = _pkce_store.pop(state, None)
    if not entry:
        return None
    if datetime.utcnow() > entry["expires_at"]:
        return None
    return entry["verifier"]


# =============================================================================
# Login attempt tracking (account lockout)
# =============================================================================

_LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
_login_attempts: Dict[str, List[float]] = {}


def _is_login_blocked(key: str, max_attempts: int) -> bool:
    """Check if a username/IP has exceeded failed login attempts."""
    now = time.time()
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < _LOGIN_ATTEMPT_WINDOW_SECONDS]
    _login_attempts[key] = attempts
    return len(attempts) >= max_attempts


def _record_failed_login(key: str) -> None:
    """Record a failed login attempt."""
    now = time.time()
    attempts = _login_attempts.get(key, [])
    attempts.append(now)
    _login_attempts[key] = attempts


def _clear_login_attempts(key: str) -> None:
    """Clear failed login attempts after successful login."""
    _login_attempts.pop(key, None)


# =============================================================================
# Safe path helper (prevent path traversal)
# =============================================================================


def _safe_path(base_dir: Path, target: str) -> Optional[Path]:
    """Resolve target relative to base_dir and ensure it stays within base_dir."""
    try:
        base = base_dir.resolve()
        target_path = Path(target)
        if not target_path.is_absolute():
            target_path = base / target_path
        resolved = target_path.resolve()
        base_str = str(base)
        resolved_str = str(resolved)
        if resolved_str == base_str or resolved_str.startswith(base_str + os.sep):
            return resolved
    except (ValueError, OSError, RuntimeError):
        pass
    return None


# =============================================================================
# Pydantic Schemas
# =============================================================================

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class VideoResponse(BaseModel):
    id: int
    filename: str
    title: Optional[str]
    description: Optional[str]
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    created_at: datetime
    modified_at: Optional[datetime]
    metadata_status: str
    thumbnail_path: Optional[str]
    printer_id: int

    class Config:
        from_attributes = True


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Dict[str, Any]] = None
    category: Optional[str] = None


class VideoDetailResponse(VideoResponse):
    printer_id: int
    original_path: str
    tags: Optional[Dict[str, Any]]
    category: Optional[str]
    processing_options: Optional[Dict[str, Any]]
    moonraker_metadata_json: Optional[Dict[str, Any]]
    processed_videos: List[Dict[str, Any]]
    uploads: List[Dict[str, Any]]


class ProcessedVideoResponse(BaseModel):
    id: int
    processed_path: str
    width: int
    height: int
    duration_seconds: float
    format: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class VideoMetadataUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None


class TextOverlayConfig(BaseModel):
    text: str
    position_x: Optional[str] = "center"
    position_y: Optional[str] = "bottom"
    text_align: Optional[str] = "center"
    font_size: Optional[int] = 36
    font_color: Optional[str] = "white"
    bg_color: Optional[str] = "black"
    bg_opacity: Optional[float] = 0.5
    border_width: Optional[int] = 0
    border_color: Optional[str] = "black"


class ProcessRequest(BaseModel):
    start_time: Optional[float] = 0.0
    duration: Optional[float] = 60.0
    output_resolution: Optional[str] = "1080x1920"
    zoom_level: Optional[float] = 0.1
    crop_mode: Optional[str] = "center"
    speed_factor: Optional[float] = None
    add_text: Optional[str] = None
    text_overlay: Optional[TextOverlayConfig] = None
    audio_track_id: Optional[int] = None
    audio_volume: Optional[float] = 0.5


class UploadCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class TikTokUploadCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    privacy_status: Optional[str] = "public"
    allow_comments: Optional[bool] = True
    allow_duet: Optional[bool] = True
    allow_stitch: Optional[bool] = True
    draft: Optional[bool] = True


class AudioTrackResponse(BaseModel):
    id: int
    name: str
    file_path: str
    duration: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class AudioTrackCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    file_path: str = Field(..., min_length=1, max_length=512)
    duration: Optional[float] = None


class PrinterResponse(BaseModel):
    id: int
    name: str
    moonraker_url: str
    api_key: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PrinterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    moonraker_url: str = Field(..., min_length=1, max_length=255)
    api_key: Optional[str] = Field(None, max_length=255)


class UploadResponse(BaseModel):
    id: int
    platform: str
    status: str
    title: Optional[str]
    upload_progress: Optional[int]
    scheduled_for: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    processed_video_id: int

    class Config:
        from_attributes = True


class AudioTrackResponse(BaseModel):
    id: int
    name: str
    file_path: str
    duration: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_videos: int
    pending_uploads: int
    published: int
    total_views: int


class SyncResponse(BaseModel):
    synced_videos: int
    message: str


# =============================================================================
# Application Setup
# =============================================================================

# Base directory for Vue SPA
BASE_DIR = Path(__file__).parent
VUE_DIST_DIR = BASE_DIR / "vue" / "dist"

app = FastAPI(
    title="Video Management System",
    description="API for managing and uploading 3D printer timelapse videos",
    version="2.0.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers."""
    return {"status": "healthy"}

# =============================================================================
# Vue SPA Serving
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_spa():
    """Serve the Vue SPA index.html."""
    index_path = VUE_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


# Mount static files from Vue dist
if (VUE_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=VUE_DIST_DIR / "assets"), name="assets")

# Keep old static files for backward compatibility
if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# =============================================================================
# Authentication Routes
# =============================================================================

@app.post("/api/auth/token", response_model=Token)
@rate_limit(max_requests=5, window=60)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate user and return JWT token."""
    client_ip = request.client.host if request.client else "unknown"
    attempt_key = f"{client_ip}:{form_data.username}"

    if _is_login_blocked(attempt_key, settings.max_login_attempts):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = get_user_by_username(db, form_data.username)
    if user is None:
        _record_failed_login(attempt_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authenticate_user(form_data.username, form_data.password, lambda _: user):
        _record_failed_login(attempt_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_login_attempts(attempt_key)

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user information."""
    return current_user


@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(max_requests=3, window=3600)
async def register_user(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user. Only available if ALLOW_REGISTRATION is enabled."""
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        )
    
    # Check if username already exists
    existing = get_user_by_username(db, user_data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )
    
    # Create new user
    user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        email=user_data.email,
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    logger.info(f"New user registered: {user_data.username}")
    return user


# =============================================================================
# Video Routes
# =============================================================================

@app.get("/api/videos", response_model=List[VideoResponse])
async def list_videos(
    sort_by: str = "date",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all videos with optional sorting."""
    query = db.query(Video)
    
    # Only show actual video files (filter by extension)
    video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
    extension_filters = []
    for ext in video_extensions:
        extension_filters.append(Video.filename.ilike(f"%{ext}"))
    query = query.filter(or_(*extension_filters))
    
    # Apply sorting
    if sort_by == "date":
        query = query.order_by(Video.modified_at.desc())
    elif sort_by == "date_oldest":
        query = query.order_by(Video.created_at.asc())
    elif sort_by == "name":
        query = query.order_by(Video.filename.asc())
    elif sort_by == "name_desc":
        query = query.order_by(Video.filename.desc())
    elif sort_by == "duration":
        query = query.order_by(Video.duration_seconds.desc())
    
    videos = query.all()
    return videos


@app.get("/api/videos/{video_id}", response_model=VideoDetailResponse)
async def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed information about a specific video."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Build response with processed videos and their uploads
    processed = []
    all_uploads = []
    for pv in video.processed_videos:
        pv_uploads = [
            {
                "id": u.id,
                "platform": u.platform,
                "status": u.status,
                "uploaded_at": u.uploaded_at,
                "error_message": u.error_message,
                "processed_video_id": pv.id,
            }
            for u in pv.uploads
        ]
        all_uploads.extend(pv_uploads)
        processed.append(
            {
                "id": pv.id,
                "format": pv.format,
                "status": pv.status,
                "duration_seconds": pv.duration_seconds,
                "width": pv.width,
                "height": pv.height,
                "created_at": pv.created_at,
                "uploads": pv_uploads,
            }
        )

    return {
        "id": video.id,
        "printer_id": video.printer_id,
        "filename": video.filename,
        "title": video.title,
        "description": video.description,
        "tags": video.tags,
        "category": video.category,
        "processing_options": video.processing_options,
        "metadata_status": video.metadata_status,
        "size_bytes": video.size_bytes,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "fps": video.fps,
        "created_at": video.created_at,
        "modified_at": video.modified_at,
        "moonraker_metadata_json": video.moonraker_metadata_json,
        "original_path": video.original_path,
        "thumbnail_path": video.thumbnail_path,
        "processed_videos": processed,
        "uploads": all_uploads,
    }


@app.put("/api/videos/{video_id}/metadata", response_model=VideoResponse)
async def update_video_metadata(
    video_id: int,
    metadata: VideoMetadataUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update video metadata."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if metadata.title is not None:
        video.title = metadata.title
    if metadata.description is not None:
        video.description = metadata.description
    if metadata.tags is not None:
        video.tags = {"tags": metadata.tags}
    if metadata.category is not None:
        video.category = metadata.category
    
    # Set metadata_status based on whether title is present
    video.metadata_status = "complete" if video.title else "pending"
    video.modified_at = datetime.utcnow()
    
    db.commit()
    db.refresh(video)
    return video


@app.get("/api/videos/{video_id}/processed", response_model=List[ProcessedVideoResponse])
async def list_processed_videos(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all processed versions of a video."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return video.processed_videos


@app.get("/api/videos/{video_id}/uploads", response_model=List[UploadResponse])
async def get_video_uploads(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get all uploads for a video across all processed versions."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    uploads = []
    for pv in video.processed_videos:
        for upload in pv.uploads:
            uploads.append(upload)
    
    return uploads


@app.post("/api/videos/{video_id}/process", response_model=ProcessedVideoResponse)
async def process_video(
    video_id: int,
    process_request: ProcessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Process a video for shorts creation."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    logger.info(f"Starting video processing for video {video_id} ({video.filename})")
    
    # Import here to avoid issues if module not available
    try:
        from video_processing.processor import VideoProcessor
    except ImportError:
        logger.error("VideoProcessor not available")
        raise HTTPException(status_code=500, detail="Video processing is not available")
    
    # Create directories
    raw_dir = Path("uploads/raw")
    processed_dir = Path("uploads/processed")
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Download file from Moonraker if needed
    raw_path = raw_dir / video.filename
    file_valid = False
    if raw_path.exists():
        file_size = raw_path.stat().st_size
        if file_size > 0:
            file_valid = True
            logger.info(f"Video already downloaded: {raw_path} ({file_size} bytes)")
        else:
            logger.warning(f"Video file exists but is empty: {raw_path}")
            os.remove(str(raw_path))
    
    if not file_valid:
        printer = db.query(Printer).filter(Printer.id == video.printer_id).first()
        if printer:
            try:
                client = MoonrakerClient(
                    base_url=printer.moonraker_url,
                    api_key=printer.api_key,
                )
                success = await client.download_timelapse(video.filename, str(raw_path))
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to download video from printer")
                file_size = raw_path.stat().st_size
                logger.info(f"Downloaded video to {raw_path} ({file_size} bytes)")
            except Exception as e:
                logger.error(f"Error downloading video: {e}")
                raise HTTPException(status_code=500, detail=f"Error downloading video: {str(e)}")
        else:
            raise HTTPException(status_code=404, detail="Printer not found for this video")
    
    # Process the video
    import time
    timestamp = int(time.time())
    output_filename = f"{video_id}_short_{timestamp}.mp4"
    output_path = processed_dir / output_filename
    
    try:
        processor = VideoProcessor(ffmpeg_path=settings.ffmpeg_path)
        
        # Build processing options
        process_options = {
            "crop_mode": process_request.crop_mode or "center",
            "target_duration": process_request.duration or 60,
            "zoom_level": process_request.zoom_level if process_request.zoom_level is not None else 1.0,
        }
        if process_request.speed_factor is not None:
            process_options["speed_factor"] = process_request.speed_factor
        if process_request.text_overlay is not None:
            process_options["text_overlay"] = process_request.text_overlay.dict()
        elif process_request.add_text is not None:
            process_options["add_text"] = process_request.add_text
        if process_request.audio_track_id is not None:
            process_options["audio_track_id"] = process_request.audio_track_id
            process_options["audio_volume"] = process_request.audio_volume if process_request.audio_volume is not None else 0.5
        
        # Process for shorts
        success = processor.process_for_shorts(
            input_path=str(raw_path),
            output_path=str(output_path),
            options=process_options,
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video processing failed")
        
        # Mix audio if specified
        if process_request.audio_track_id is not None:
            audio_track = db.query(AudioTrack).filter(
                AudioTrack.id == process_request.audio_track_id,
            ).first()
            if audio_track and os.path.exists(audio_track.file_path):
                logger.info(f"Mixing audio track: {audio_track.name}")
                try:
                    from post_processing.audio_mixer import AudioMixer
                    mixer = AudioMixer(ffmpeg_path=settings.ffmpeg_path)
                    temp_output = str(output_path) + ".audio.mp4"
                    success = mixer.mix_audio(
                        video_path=str(output_path),
                        audio_path=audio_track.file_path,
                        output_path=temp_output,
                        volume=process_request.audio_volume if process_request.audio_volume is not None else 0.5,
                    )
                    if success:
                        os.replace(temp_output, str(output_path))
                        logger.info("Audio mixed successfully")
                    else:
                        if os.path.exists(temp_output):
                            os.remove(temp_output)
                except ImportError:
                    logger.warning("AudioMixer not available")
        
        # Get info about processed video
        info = processor.get_video_info(str(output_path))
        
        # Create processed video record
        processed = ProcessedVideo(
            video_id=video_id,
            processed_path=str(output_path),
            width=info.get("width", 1080) if info else 1080,
            height=info.get("height", 1920) if info else 1920,
            duration_seconds=info.get("duration", 60.0) if info else 60.0,
            format="mp4",
            status="completed",
        )
        
        db.add(processed)
        db.commit()
        db.refresh(processed)
        
        return processed
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing video: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {str(e)}")


@app.delete("/api/videos/{video_id}/processed/{processed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_processed_video_endpoint(
    video_id: int,
    processed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a processed video version."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    processed = db.query(ProcessedVideo).filter(
        ProcessedVideo.id == processed_id,
        ProcessedVideo.video_id == video_id,
    ).first()
    
    if not processed:
        raise HTTPException(status_code=404, detail="Processed video not found")
    
    # Delete associated uploads first
    for upload in processed.uploads:
        db.delete(upload)
    
    # Delete the file from disk
    try:
        safe_path = _safe_path(BASE_DIR.parent, processed.processed_path)
        if safe_path and safe_path.exists():
            os.remove(safe_path)
    except OSError as e:
        logger.error(f"Failed to delete processed video file: {e}")
    
    db.delete(processed)
    db.commit()


@app.get("/api/videos/{video_id}/processed/{processed_id}/download")
async def download_processed_video(
    video_id: int,
    processed_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Download a processed video file. Requires authentication."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    processed = db.query(ProcessedVideo).filter(
        ProcessedVideo.id == processed_id,
        ProcessedVideo.video_id == video_id,
    ).first()
    
    if not processed:
        raise HTTPException(status_code=404, detail="Processed video not found")
    
    safe_path = _safe_path(BASE_DIR.parent, processed.processed_path)
    if not safe_path or not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    return FileResponse(
        safe_path,
        media_type="video/mp4",
        filename=safe_path.name
    )


# =============================================================================
# Upload Routes
# =============================================================================

@app.get("/api/uploads", response_model=List[UploadResponse])
async def list_uploads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all uploads."""
    uploads = db.query(Upload).order_by(Upload.updated_at.desc()).all()
    return uploads


@app.get("/api/uploads/{upload_id}", response_model=UploadResponse)
async def get_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific upload by ID."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


@app.post("/api/uploads/{upload_id}/retry")
async def retry_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Retry a failed upload."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    upload.status = "queued"
    upload.retry_count += 1
    upload.error_message = None
    db.commit()
    
    return {"message": "Upload queued for retry"}


@app.post("/api/uploads/{upload_id}/cancel")
async def cancel_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cancel an upload."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    upload.status = "cancelled"
    db.commit()
    
    return {"message": "Upload cancelled"}


@app.post("/api/uploads/youtube/{processed_id}", response_model=UploadResponse)
async def upload_to_youtube(
    processed_id: int,
    upload_data: UploadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload a processed video to YouTube."""
    processed = db.query(ProcessedVideo).filter(ProcessedVideo.id == processed_id).first()
    if not processed:
        raise HTTPException(status_code=404, detail="Processed video not found")
    
    if processed.status != "completed":
        raise HTTPException(status_code=400, detail="Video processing not completed")
    
    # Create upload record
    upload = Upload(
        processed_video_id=processed_id,
        platform="youtube",
        status="pending",
        title=upload_data.title or processed.video.filename,
        description=upload_data.description,
        tags={"tags": upload_data.tags} if upload_data.tags else None,
    )
    
    db.add(upload)
    db.commit()
    db.refresh(upload)
    
    # Start YouTube upload
    logger.info(f"[YouTube Upload] Starting upload for processed_video_id={processed_id}, upload_id={upload.id}")
    
    try:
        from uploaders.youtube import YouTubeUploader
        
        uploader = YouTubeUploader()
        token_path = getattr(settings, 'youtube_token_path', 'data/youtube_token.json')
        
        if not os.path.exists(token_path):
            upload.status = "failed"
            upload.error_message = "YouTube token not found. Please authenticate first."
            db.commit()
            raise HTTPException(status_code=400, detail=upload.error_message)
        
        # Update status to uploading
        upload.status = "uploading"
        db.commit()
        
        # Authenticate and upload
        auth_success = False
        client_secrets_path = getattr(settings, 'youtube_client_secrets_path', None)
        
        if client_secrets_path and os.path.exists(client_secrets_path):
            auth_success = uploader.authenticate(client_secrets_path, token_path)
        else:
            # Try to load token directly
            try:
                import json
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                
                with open(token_path, 'r') as f:
                    token_data = json.load(f)
                
                credentials = Credentials.from_authorized_user_info(token_data, [
                    "https://www.googleapis.com/auth/youtube.force-ssl",
                    "https://www.googleapis.com/auth/youtube.upload",
                ])
                
                if credentials.valid:
                    uploader.credentials = credentials
                    uploader.service = build("youtube", "v3", credentials=credentials)
                    auth_success = True
                elif credentials.expired and credentials.refresh_token:
                    from google.auth.transport.requests import Request
                    credentials.refresh(Request())
                    uploader.credentials = credentials
                    uploader.service = build("youtube", "v3", credentials=credentials)
                    auth_success = True
            except Exception as e:
                logger.error(f"Failed to load YouTube token: {e}")
        
        if not auth_success:
            upload.status = "failed"
            upload.error_message = "YouTube authentication failed"
            db.commit()
            raise HTTPException(status_code=400, detail="YouTube authentication failed")
        
        # Extract tags and append to description
        tags = upload_data.tags or []
        description = upload_data.description or ""
        if tags:
            tag_lines = "\n\n" + " ".join([f"#{tag}" for tag in tags])
            description = description + tag_lines
        
        # Upload to YouTube
        success, video_id, error = uploader.upload_video(
            video_path=processed.processed_path,
            title=upload.title,
            description=description,
            tags=[],
            category_id="22",
            privacy_status="private",
        )
        
        if success and video_id:
            upload.status = "completed"
            upload.platform_video_id = video_id
            upload.upload_url = f"https://youtube.com/watch?v={video_id}"
            upload.uploaded_at = datetime.utcnow()
            db.commit()
            logger.info(f"[YouTube Upload] SUCCESS! Video ID: {video_id}")
        else:
            error_msg = f"YouTube upload failed: {error.get('message', 'Unknown error')}" if error else "YouTube upload failed"
            upload.status = "failed"
            upload.error_message = error_msg
            db.commit()
            raise HTTPException(status_code=500, detail=error_msg)
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        logger.exception(f"[YouTube Upload] {error_msg}")
        upload.status = "failed"
        upload.error_message = error_msg
        db.commit()
        raise HTTPException(status_code=500, detail=error_msg)
    
    return upload


@app.post("/api/uploads/tiktok/{processed_id}", response_model=UploadResponse)
async def upload_to_tiktok(
    processed_id: int,
    upload_data: TikTokUploadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Queue a processed video for TikTok upload."""
    processed = db.query(ProcessedVideo).filter(ProcessedVideo.id == processed_id).first()
    if not processed:
        raise HTTPException(status_code=404, detail="Processed video not found")
    
    if processed.status != "completed":
        raise HTTPException(status_code=400, detail="Video processing not completed")
    
    # Check TikTok is enabled
    if not getattr(settings, 'enable_tiktok_upload', False):
        raise HTTPException(status_code=400, detail="TikTok upload is disabled")
    
    # Check credentials
    if not getattr(settings, 'tiktok_client_key', None) or not getattr(settings, 'tiktok_client_secret', None):
        raise HTTPException(status_code=400, detail="TikTok credentials not configured")
    
    token_path = getattr(settings, 'tiktok_token_file', None)
    if not token_path or not os.path.exists(token_path):
        raise HTTPException(status_code=400, detail="TikTok not authenticated")
    
    # Build tags with TikTok-specific options
    tags = {"tags": upload_data.tags} if upload_data.tags else {}
    privacy_status = upload_data.privacy_status or getattr(settings, 'tiktok_default_privacy', 'private')
    
    # Force private for unaudited apps
    if privacy_status != "private":
        privacy_status = "private"
    
    tags["privacy_status"] = privacy_status
    tags["allow_comments"] = upload_data.allow_comments
    tags["allow_duet"] = upload_data.allow_duet
    tags["allow_stitch"] = upload_data.allow_stitch
    tags["draft"] = upload_data.draft
    
    # Create upload record
    upload = Upload(
        processed_video_id=processed_id,
        platform="tiktok",
        status="queued",
        title=upload_data.title or processed.video.title or processed.video.filename,
        description=upload_data.description,
        tags=tags,
    )
    
    db.add(upload)
    db.commit()
    db.refresh(upload)
    
    logger.info(f"[TikTok Upload] Queued upload for processed_video_id={processed_id}, upload_id={upload.id}")
    
    return upload


# =============================================================================
# Audio Track Routes
# =============================================================================

@app.get("/api/audio", response_model=List[AudioTrackResponse])
async def list_audio_tracks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all audio tracks."""
    tracks = db.query(AudioTrack).all()
    return tracks


@app.post("/api/audio", response_model=AudioTrackResponse, status_code=status.HTTP_201_CREATED)
async def create_audio_track(
    track_data: AudioTrackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new audio track record."""
    track = AudioTrack(
        name=track_data.name,
        file_path=track_data.file_path,
        duration=track_data.duration,
        user_id=current_user.id,
    )
    db.add(track)
    db.commit()
    db.refresh(track)
    logger.info(f"Created audio track: {track.name} (id={track.id})")
    return track


@app.delete("/api/audio/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audio_track(
    track_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete an audio track."""
    track = db.query(AudioTrack).filter(AudioTrack.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Audio track not found")
    db.delete(track)
    db.commit()


# =============================================================================
# Printer Routes
# =============================================================================

@app.get("/api/printers", response_model=List[PrinterResponse])
async def list_printers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all configured printers."""
    printers = db.query(Printer).all()
    return printers


@app.post("/api/printers", response_model=PrinterResponse, status_code=status.HTTP_201_CREATED)
async def create_printer_route(
    printer_data: PrinterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new printer."""
    printer = Printer(
        name=printer_data.name,
        moonraker_url=printer_data.moonraker_url,
        api_key=printer_data.api_key,
        is_active=True,
    )
    db.add(printer)
    db.commit()
    db.refresh(printer)
    logger.info(f"Created printer: {printer.name} (id={printer.id})")
    return printer


@app.delete("/api/printers/{printer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_printer_route(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a printer and all associated data."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    videos = db.query(Video).filter(Video.printer_id == printer_id).all()
    for video in videos:
        for processed in list(video.processed_videos):
            for upload in list(processed.uploads):
                for analytics in list(upload.analytics):
                    db.delete(analytics)
                db.query(UploadJob).filter(UploadJob.upload_id == upload.id).delete(
                    synchronize_session=False
                )
                db.delete(upload)
            for overlay in list(processed.text_overlays):
                db.delete(overlay)
            for va in list(processed.video_audios):
                db.delete(va)
            safe_path = _safe_path(BASE_DIR.parent, processed.processed_path)
            if safe_path and safe_path.exists():
                try:
                    os.remove(safe_path)
                except OSError as e:
                    logger.error(f"Failed to delete processed video file: {e}")
            db.delete(processed)
        db.delete(video)

    zip_archives = db.query(ZipArchive).filter(ZipArchive.printer_id == printer_id).all()
    for z in zip_archives:
        db.delete(z)

    db.delete(printer)
    db.commit()
    logger.info(f"Deleted printer: id={printer_id}")
    return None


@app.post("/api/printers/{printer_id}/sync", response_model=SyncResponse)
async def sync_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Sync videos from a printer."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    
    try:
        client = MoonrakerClient(printer.moonraker_url, printer.api_key)
        videos = await client.get_timelapse_files()
        
        synced_count = 0
        for video_data in videos:
            # Check if video already exists
            existing = db.query(Video).filter(
                Video.original_path == video_data["path"]
            ).first()
            
            if not existing:
                video = Video(
                    printer_id=printer_id,
                    filename=video_data["path"],
                    original_path=video_data["path"],
                    size_bytes=video_data.get("size", 0),
                    duration_seconds=video_data.get("duration", 0),
                    width=video_data.get("width", 0),
                    height=video_data.get("height", 0),
                    fps=video_data.get("fps", 0),
                    thumbnail_path=video_data.get("thumbnail"),
                    metadata_status="pending"
                )
                db.add(video)
                synced_count += 1
        
        db.commit()
        
        return SyncResponse(
            synced_videos=synced_count,
            message=f"Successfully synced {synced_count} videos"
        )
    
    except Exception as e:
        logger.error(f"Sync failed for printer {printer_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Audio Track Routes
# =============================================================================

@app.get("/api/audio-tracks", response_model=List[AudioTrackResponse])
async def list_audio_tracks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all audio tracks."""
    tracks = db.query(AudioTrack).order_by(AudioTrack.created_at.desc()).all()
    return tracks


# =============================================================================
# Dashboard Stats
# =============================================================================

@app.get("/api/stats/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get dashboard statistics."""
    total_videos = db.query(Video).count()
    pending_uploads = db.query(Upload).filter(
        Upload.status.in_(["queued", "pending", "uploading"])
    ).count()
    published = db.query(Upload).filter(Upload.status == "completed").count()
    
    # Calculate total views from analytics
    total_views = db.query(func.sum(VideoAnalytics.views)).scalar() or 0
    
    return DashboardStats(
        total_videos=total_videos,
        pending_uploads=pending_uploads,
        published=published,
        total_views=total_views
    )


# =============================================================================
# Analytics Routes
# =============================================================================

@app.get("/api/analytics")
async def get_analytics(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get analytics data for the specified time period."""
    from_date = datetime.utcnow() - timedelta(days=days)
    
    analytics = db.query(VideoAnalytics).filter(
        VideoAnalytics.collected_at >= from_date
    ).all()
    
    return {
        "total_views": sum(a.views for a in analytics),
        "total_likes": sum(a.likes for a in analytics),
        "total_comments": sum(a.comments for a in analytics),
        "total_shares": sum(a.shares for a in analytics),
        "period_days": days
    }


# =============================================================================
# Platform Settings Routes
# =============================================================================

@app.get("/api/settings")
async def get_settings(
    current_user: User = Depends(get_current_active_user)
):
    """Get platform settings."""
    # Check YouTube connection and get account info if available
    youtube_connected = False
    youtube_email = None
    if settings.youtube_token_file and os.path.exists(settings.youtube_token_file):
        youtube_connected = True
        try:
            import json
            with open(settings.youtube_token_file, 'r') as f:
                token_data = json.load(f)
            # Try to get email from token if available
            if isinstance(token_data, dict):
                youtube_email = token_data.get('email', 'Connected')
        except Exception:
            pass
    
    # Check TikTok connection
    tiktok_connected = False
    if settings.tiktok_token_file and os.path.exists(settings.tiktok_token_file):
        tiktok_connected = True
    
    return {
        "youtube_connected": youtube_connected,
        "youtube_email": youtube_email,
        "tiktok_connected": tiktok_connected,
        "tiktok_default_privacy": settings.tiktok_default_privacy,
        "processing_defaults": {
            "resolution": settings.output_resolution,
            "max_duration": settings.max_video_duration,
            "crop_mode": settings.default_crop_mode,
            "zoom_level": settings.default_zoom_level
        },
        "moonraker_url": settings.moonraker_url,
        "features": {
            "enable_tiktok_upload": settings.enable_tiktok_upload,
            "enable_post_processing": settings.enable_post_processing,
            "enable_bulk_operations": settings.enable_bulk_operations
        },
        "upload_settings": {
            "max_concurrent_uploads": settings.max_concurrent_uploads,
            "max_upload_retries": settings.max_upload_retries
        }
    }


@app.put("/api/settings")
async def update_settings(
    update: dict,
    current_user: User = Depends(get_current_active_user)
):
    """Update platform settings."""
    # Note: In a production environment, you would persist these to a database
    # For now, we return the updated settings (they won't persist across restarts)
    # The user should update the .env file for persistent changes
    
    return {
        "message": "Settings updated. Note: Some settings require updating the .env file to persist across restarts.",
        "settings": update
    }


# =============================================================================
# TikTok Auth Routes
# =============================================================================

class TikTokAuthUrlResponse(BaseModel):
    auth_url: str
    message: str


class TikTokTokenResponse(BaseModel):
    success: bool
    message: str
    expires_in: Optional[int] = None


class TikTokAccountResponse(BaseModel):
    connected: bool
    username: Optional[str] = None
    follower_count: Optional[int] = None
    avatar_url: Optional[str] = None


@app.get("/api/tiktok/auth", response_model=TikTokAuthUrlResponse)
async def get_tiktok_auth_url(
    current_user: User = Depends(get_current_active_user),
):
    """Get TikTok OAuth2 authorization URL."""
    if not settings.tiktok_client_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TikTok client key not configured",
        )

    from urllib.parse import quote
    from uploaders.tiktok import OAUTH_AUTHORIZE_URL

    scopes = "video.upload,video.publish,user.info.basic"
    import secrets
    state = secrets.token_urlsafe(32)

    code_verifier, code_challenge = _generate_pkce()
    _store_pkce_verifier(state, code_verifier)

    params = {
        "client_key": settings.tiktok_client_key,
        "redirect_uri": settings.tiktok_redirect_uri,
        "scope": scopes,
        "response_type": "code",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query_string = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in params.items())

    auth_url = f"{OAUTH_AUTHORIZE_URL}?{query_string}"

    logger.info(f"Generated TikTok auth URL for user {current_user.username} (with PKCE)")

    return {
        "auth_url": auth_url,
        "message": "Visit this URL to authorize TikTok access",
    }


@app.get("/api/tiktok/auth/callback")
async def tiktok_auth_callback(
    code: str,
    state: Optional[str] = None,
):
    """Handle TikTok OAuth2 callback."""
    if not settings.tiktok_client_key or not settings.tiktok_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TikTok credentials not configured",
        )

    code_verifier = None
    if state:
        code_verifier = _get_pkce_verifier(state)
        if not code_verifier:
            logger.warning(f"PKCE verifier not found or expired for state={state}")

    from uploaders.tiktok import TikTokUploader

    uploader = TikTokUploader(
        client_key=settings.tiktok_client_key,
        client_secret=settings.tiktok_client_secret,
    )
    uploader.token_path = settings.tiktok_token_file

    logger.info("Exchanging TikTok auth code from callback")
    success = uploader.authenticate(
        auth_code=code,
        redirect_uri=settings.tiktok_redirect_uri,
        code_verifier=code_verifier,
    )

    if success:
        logger.info("TikTok authentication successful")
        return {
            "success": True,
            "message": "TikTok account connected successfully. You can close this window.",
        }
    else:
        logger.error("TikTok authentication failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to authenticate with TikTok. Invalid code or credentials.",
        )


@app.post("/api/tiktok/auth/refresh", response_model=TikTokTokenResponse)
async def refresh_tiktok_token(
    current_user: User = Depends(get_current_active_user),
):
    """Manually refresh TikTok access token."""
    from uploaders.tiktok import TikTokUploader

    uploader = TikTokUploader(
        client_key=settings.tiktok_client_key,
        client_secret=settings.tiktok_client_secret,
    )
    uploader.token_path = settings.tiktok_token_file

    if not uploader.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not authenticated with TikTok",
        )

    logger.info(f"Refreshing TikTok token for user {current_user.username}")
    success = uploader.refresh_token()

    if success:
        expires_in = int(uploader._token_expires_at - time.time()) if uploader._token_expires_at else None
        return {
            "success": True,
            "message": "Token refreshed successfully",
            "expires_in": expires_in,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refresh token. Please re-authenticate.",
        )


@app.get("/api/tiktok/account", response_model=TikTokAccountResponse)
async def get_tiktok_account(
    current_user: User = Depends(get_current_active_user),
):
    """Get connected TikTok account info."""
    from uploaders.tiktok import TikTokUploader

    uploader = TikTokUploader(
        client_key=settings.tiktok_client_key,
        client_secret=settings.tiktok_client_secret,
    )
    uploader.token_path = settings.tiktok_token_file

    if not uploader.is_authenticated():
        logger.info("TikTok not authenticated - no valid token found")
        return {"connected": False}

    logger.info("TikTok authenticated - token is valid")
    return {"connected": True}


# =============================================================================
# Vue SPA Catch-All Route (MUST be last to avoid conflicts with API routes)
# =============================================================================

@app.get("/{path:path}")
async def serve_spa_routes(path: str):
    """Serve Vue Router routes by returning index.html for non-API paths."""
    # Skip API routes
    if path.startswith("api/") or path.startswith("static/"):
        raise HTTPException(status_code=404)

    # Try to serve static files first (prevent path traversal)
    safe_file_path = _safe_path(VUE_DIST_DIR, path)
    if safe_file_path and safe_file_path.is_file():
        return FileResponse(safe_file_path)

    # Fall back to index.html for client-side routing
    index_path = VUE_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)