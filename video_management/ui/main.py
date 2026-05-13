"""FastAPI web interface for the video management system."""

import logging
import os
from datetime import datetime, timedelta
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_current_user,
    get_password_hash,
    oauth2_scheme,
)
from auth.dependencies import override_get_user
from config import settings
from api.moonraker import MoonrakerClient
from database import get_db, SessionLocal
from database.models import (
    Printer,
    ProcessedVideo,
    Upload,
    User,
    Video,
    VideoAnalytics,
)

logger = logging.getLogger(__name__)


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
    password: str = Field(..., min_length=6)
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
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    created_at: datetime

    class Config:
        from_attributes = True


class VideoDetailResponse(VideoResponse):
    printer_id: int
    original_path: str
    moonraker_metadata_json: Optional[Dict[str, Any]]
    processed_videos: List[Dict[str, Any]]


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


class UploadResponse(BaseModel):
    id: int
    platform: str
    platform_video_id: Optional[str]
    status: str
    upload_url: Optional[str]
    title: Optional[str]
    uploaded_at: Optional[datetime]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class UploadCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class PrinterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    moonraker_url: str = Field(..., min_length=1)
    api_key: Optional[str] = None


class PrinterResponse(BaseModel):
    id: int
    name: str
    moonraker_url: str
    api_key: Optional[str]
    is_active: bool
    created_at: datetime
    video_count: int

    class Config:
        from_attributes = True


class AnalyticsResponse(BaseModel):
    total_uploads: int
    total_views: int
    total_likes: int
    total_comments: int
    platform_breakdown: Dict[str, Dict[str, int]]
    recent_uploads: List[Dict[str, Any]]


class UploadAnalyticsResponse(BaseModel):
    upload_id: int
    views: int
    likes: int
    comments: int
    shares: int
    collected_at: datetime

    class Config:
        from_attributes = True


class ProcessRequest(BaseModel):
    start_time: Optional[float] = 0.0
    duration: Optional[float] = 60.0
    output_resolution: Optional[str] = "1080x1920"


# =============================================================================
# FastAPI App Setup
# =============================================================================

app = FastAPI(
    title="Video Management System",
    description="Web interface for managing 3D printer videos, processing, and uploads",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="ui/static"), name="static")
templates = Jinja2Templates(directory="ui/templates")


# =============================================================================
# Security Tracking
# =============================================================================

# Simple in-memory tracking for failed login attempts
# In production, consider using Redis or database tracking
_login_attempts: Dict[str, List[datetime]] = {}


def _check_login_attempts(username: str) -> bool:
    """Check if user has exceeded max login attempts."""
    now = datetime.utcnow()
    attempts = _login_attempts.get(username, [])
    # Keep only attempts from last 15 minutes
    recent_attempts = [a for a in attempts if now - a < timedelta(minutes=15)]
    _login_attempts[username] = recent_attempts
    return len(recent_attempts) < settings.max_login_attempts


def _record_failed_login(username: str) -> None:
    """Record a failed login attempt."""
    if username not in _login_attempts:
        _login_attempts[username] = []
    _login_attempts[username].append(datetime.utcnow())


# =============================================================================
# Helper Functions
# =============================================================================

def get_user_by_username(username: str, db: Session) -> Optional[User]:
    """Get user by username from database."""
    return db.query(User).filter(User.username == username).first()


def _get_user_for_auth(username: str) -> Optional[User]:
    """Get user by username for auth dependencies (no db parameter)."""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


# Wire up the auth dependency to use our database
override_get_user(_get_user_for_auth)


def _count_users(db: Session) -> int:
    """Count total number of users in database."""
    return db.query(User).count()


# =============================================================================
# Web Routes (HTML Pages)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Any:
    """Render the main dashboard page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> Any:
    """Render the login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> Any:
    """Render the dashboard page."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request},
    )


@app.get("/videos", response_class=HTMLResponse)
async def videos_page(request: Request) -> Any:
    """Render the videos page."""
    return templates.TemplateResponse(
        "videos.html",
        {"request": request},
    )


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request) -> Any:
    """Render the analytics page."""
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request},
    )


@app.get("/printers", response_class=HTMLResponse)
async def printers_page(request: Request) -> Any:
    """Render the printers page."""
    return templates.TemplateResponse(
        "printers.html",
        {"request": request},
    )


@app.get("/uploads", response_class=HTMLResponse)
async def uploads_page(request: Request) -> Any:
    """Render the uploads page."""
    return templates.TemplateResponse(
        "uploads.html",
        {"request": request},
    )


@app.get("/videos/{video_id}", response_class=HTMLResponse)
async def video_detail_page(
    video_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Render the video detail page."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    return templates.TemplateResponse(
        "video_detail.html",
        {"request": request, "video": video},
    )


# =============================================================================
# Authentication Routes
# =============================================================================

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)) -> Any:
    """Register a new user.
    
    Registration is only allowed if:
    1. ALLOW_REGISTRATION environment variable is set to true, OR
    2. No users exist yet (first user bootstrap)
    """
    user_count = _count_users(db)
    
    # Check if registration is allowed
    if user_count > 0 and not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled. Contact administrator for access.",
        )
    
    # Check if username already exists
    existing_user = get_user_by_username(user_data.username, db)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        email=user_data.email,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"New user registered: {user_data.username}")

    return new_user


@auth_router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_admin(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Create a new user (admin only).
    
    This endpoint allows existing authenticated users to create new accounts.
    Useful when public registration is disabled.
    """
    # Check if username already exists
    existing_user = get_user_by_username(user_data.username, db)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        email=user_data.email,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"User created by admin {current_user.username}: {user_data.username}")

    return new_user


@auth_router.post("/login", response_model=Token)
async def login(form_data: UserLogin, db: Session = Depends(get_db)) -> Any:
    """Authenticate user and return JWT token.
    
    Rate limiting: After 5 failed attempts within 15 minutes,
    the account is temporarily locked.
    """
    # Check rate limiting
    if not _check_login_attempts(form_data.username):
        logger.warning(f"Login blocked for user {form_data.username} due to too many failed attempts")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please try again in 15 minutes.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = get_user_by_username(form_data.username, db)
    if user is None:
        _record_failed_login(form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authenticate_user(form_data.username, form_data.password, lambda u: user):
        _record_failed_login(form_data.username)
        logger.warning(f"Failed login attempt for user {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )

    return {"access_token": access_token, "token_type": "bearer"}


app.include_router(auth_router)


# =============================================================================
# Video Routes
# =============================================================================

video_router = APIRouter(prefix="/api/videos", tags=["Videos"])


@video_router.get("/", response_model=List[VideoResponse])
async def list_videos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List all videos with pagination."""
    videos = db.query(Video).offset(skip).limit(limit).all()
    logger.info(f"Listed {len(videos)} videos (skip={skip}, limit={limit})")
    if not videos:
        logger.info("No videos found in database. Try syncing a printer first.")
    return videos


@video_router.get("/{video_id}", response_model=VideoDetailResponse)
async def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get detailed information about a specific video."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    # Build response with processed videos
    processed = [
        {
            "id": pv.id,
            "format": pv.format,
            "status": pv.status,
            "duration_seconds": pv.duration_seconds,
            "created_at": pv.created_at,
        }
        for pv in video.processed_videos
    ]

    return {
        "id": video.id,
        "printer_id": video.printer_id,
        "filename": video.filename,
        "original_path": video.original_path,
        "size_bytes": video.size_bytes,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "fps": video.fps,
        "created_at": video.created_at,
        "moonraker_metadata_json": video.moonraker_metadata_json,
        "processed_videos": processed,
    }


@video_router.post("/{video_id}/process", response_model=ProcessedVideoResponse)
async def process_video(
    video_id: int,
    process_request: ProcessRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Process a video for shorts creation."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    logger.info(f"Starting video processing for video {video_id} ({video.filename})")

    # Download the video from Moonraker first
    import os
    from pathlib import Path
    from video_processing.processor import VideoProcessor

    # Create directories
    raw_dir = Path("uploads/raw")
    processed_dir = Path("uploads/processed")
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Download file from Moonraker
    raw_path = raw_dir / video.filename
    
    # Check if already downloaded and valid
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
        logger.info(f"Downloading video from Moonraker: {video.filename}")
        printer = db.query(Printer).filter(Printer.id == video.printer_id).first()
        if printer:
            try:
                client = MoonrakerClient(
                    base_url=printer.moonraker_url,
                    api_key=printer.api_key,
                )
                success = await client.download_timelapse(video.filename, str(raw_path))
                if not success:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to download video from printer",
                    )
                file_size = raw_path.stat().st_size
                logger.info(f"Downloaded video to {raw_path} ({file_size} bytes)")
                
                # Validate downloaded file
                if file_size == 0:
                    os.remove(str(raw_path))
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Downloaded file is empty",
                    )
                    
                # Quick validation with ffprobe
                try:
                    processor = VideoProcessor(ffmpeg_path=settings.ffmpeg_path)
                    info = processor.get_video_info(str(raw_path))
                    if not info:
                        logger.warning(f"Downloaded file failed validation, removing: {raw_path}")
                        os.remove(str(raw_path))
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Downloaded file is corrupted or invalid",
                        )
                    logger.info(f"Downloaded file validated: {info['width']}x{info['height']}, {info['duration']}s")
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error validating downloaded file: {e}")
            except Exception as e:
                logger.error(f"Error downloading video: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error downloading video: {str(e)}",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Printer not found for this video",
            )

    # Process the video
    output_filename = f"{video_id}_short.mp4"
    output_path = processed_dir / output_filename

    logger.info(f"Processing video for shorts: {raw_path} -> {output_path}")

    try:
        processor = VideoProcessor(ffmpeg_path=settings.ffmpeg_path)
        
        # Process for shorts
        success = processor.process_for_shorts(
            input_path=str(raw_path),
            output_path=str(output_path),
            options={
                "crop_mode": "center",
                "target_duration": process_request.duration or 60,
            }
        )

        if not success:
            # Check if input file is corrupted
            file_size = raw_path.stat().st_size if raw_path.exists() else 0
            logger.error(f"Video processing failed for {raw_path} ({file_size} bytes)")
            
            # If file exists but is very small or processing failed, it might be corrupted
            if file_size > 0 and file_size < 1024:  # Less than 1KB is suspicious
                logger.warning(f"Input file seems corrupted (too small), removing: {raw_path}")
                os.remove(str(raw_path))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Video file was corrupted and has been removed. Please retry.",
                )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Video processing failed. The file may be corrupted - try deleting and re-downloading.",
            )

        # Get info about processed video
        info = processor.get_video_info(str(output_path))
        
        logger.info(f"Video processing completed: {output_path}")

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

        logger.info(f"Created processed video record: {processed.id}")

        return processed

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing video: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing video: {str(e)}",
        )


@video_router.get("/{video_id}/processed", response_model=List[ProcessedVideoResponse])
async def list_processed_videos(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List all processed versions of a video."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    return video.processed_videos


app.include_router(video_router)


# =============================================================================
# Upload Routes
# =============================================================================

upload_router = APIRouter(prefix="/api/uploads", tags=["Uploads"])


@upload_router.post("/youtube/{processed_id}", response_model=UploadResponse)
async def upload_to_youtube(
    processed_id: int,
    upload_data: UploadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Upload a processed video to YouTube."""
    processed = db.query(ProcessedVideo).filter(ProcessedVideo.id == processed_id).first()
    if processed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed video not found",
        )

    if processed.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video processing not completed",
        )

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
    logger.info(f"[YouTube Upload] Video file: {processed.processed_path}")
    logger.info(f"[YouTube Upload] Title: {upload.title}")
    
    # Update status to uploading
    upload.status = "uploading"
    db.commit()
    logger.info(f"[YouTube Upload] Status updated to 'uploading' for upload_id={upload.id}")

    try:
        # Import and initialize YouTube uploader
        from uploaders.youtube import YouTubeUploader
        
        logger.info("[YouTube Upload] Initializing YouTubeUploader...")
        uploader = YouTubeUploader()
        
        # Check for token file
        token_path = getattr(settings, 'youtube_token_path', 'data/youtube_token.json')
        client_secrets_path = getattr(settings, 'youtube_client_secrets_path', None)
        
        logger.info(f"[YouTube Upload] Looking for token at: {token_path}")
        logger.info(f"[YouTube Upload] Token exists: {os.path.exists(token_path)}")
        
        if not os.path.exists(token_path):
            error_msg = f"YouTube token not found at {token_path}. Please authenticate first."
            logger.error(f"[YouTube Upload] {error_msg}")
            upload.status = "failed"
            upload.error_message = error_msg
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        
        # Authenticate
        logger.info("[YouTube Upload] Authenticating with YouTube...")
        auth_success = False
        
        if client_secrets_path and os.path.exists(client_secrets_path):
            auth_success = uploader.authenticate(client_secrets_path, token_path)
        else:
            # Try to load token directly without client secrets (if token is valid)
            logger.info("[YouTube Upload] No client secrets found, attempting to load existing token...")
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
                    uploader.token_path = token_path
                    auth_success = True
                    logger.info("[YouTube Upload] Token loaded successfully")
                elif credentials.expired and credentials.refresh_token:
                    from google.auth.transport.requests import Request
                    credentials.refresh(Request())
                    uploader.credentials = credentials
                    uploader.service = build("youtube", "v3", credentials=credentials)
                    uploader.token_path = token_path
                    auth_success = True
                    logger.info("[YouTube Upload] Token refreshed successfully")
                else:
                    logger.error("[YouTube Upload] Token is invalid and cannot be refreshed")
            except Exception as e:
                logger.error(f"[YouTube Upload] Failed to load token: {e}")
        
        if not auth_success:
            error_msg = "YouTube authentication failed. Please check your credentials."
            logger.error(f"[YouTube Upload] {error_msg}")
            upload.status = "failed"
            upload.error_message = error_msg
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        
        logger.info("[YouTube Upload] Authentication successful")
        
        # Extract tags
        tags = upload_data.tags or []
        if upload.tags and isinstance(upload.tags, dict):
            tags = upload.tags.get("tags", tags)
        
        logger.info(f"[YouTube Upload] Tags: {tags}")
        logger.info(f"[YouTube Upload] Description: {upload_data.description or ''}")
        
        # Upload the video
        logger.info(f"[YouTube Upload] Beginning video upload...")
        video_id = uploader.upload_video(
            video_path=processed.processed_path,
            title=upload.title,
            description=upload_data.description or "",
            tags=tags,
            category_id="22",  # People & Blogs
            privacy_status="private",  # Default to private
        )
        
        if video_id:
            # Success!
            upload.status = "completed"
            upload.platform_video_id = video_id
            upload.upload_url = f"https://youtube.com/watch?v={video_id}"
            upload.uploaded_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"[YouTube Upload] SUCCESS! Video ID: {video_id}")
            logger.info(f"[YouTube Upload] URL: https://youtube.com/watch?v={video_id}")
            logger.info(f"[YouTube Upload] Upload completed at: {upload.uploaded_at}")
        else:
            # Upload failed but no exception
            error_msg = "YouTube upload failed. Check server logs for details."
            logger.error(f"[YouTube Upload] {error_msg}")
            upload.status = "failed"
            upload.error_message = error_msg
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_msg,
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Upload failed: {str(e)}"
        logger.exception(f"[YouTube Upload] {error_msg}")
        upload.status = "failed"
        upload.error_message = error_msg
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )

    return upload


@upload_router.post("/tiktok/{processed_id}", response_model=UploadResponse)
async def upload_to_tiktok(
    processed_id: int,
    upload_data: UploadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Upload a processed video to TikTok."""
    processed = db.query(ProcessedVideo).filter(ProcessedVideo.id == processed_id).first()
    if processed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed video not found",
        )

    if processed.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video processing not completed",
        )

    # Create upload record
    upload = Upload(
        processed_video_id=processed_id,
        platform="tiktok",
        status="pending",
        title=upload_data.title or processed.video.filename,
        description=upload_data.description,
        tags={"tags": upload_data.tags} if upload_data.tags else None,
    )

    db.add(upload)
    db.commit()
    db.refresh(upload)

    # Start TikTok upload
    logger.info(f"[TikTok Upload] Starting upload for processed_video_id={processed_id}, upload_id={upload.id}")
    logger.info(f"[TikTok Upload] Video file: {processed.processed_path}")
    logger.info(f"[TikTok Upload] Title: {upload.title}")
    
    # Update status to uploading
    upload.status = "uploading"
    db.commit()
    logger.info(f"[TikTok Upload] Status updated to 'uploading' for upload_id={upload.id}")

    try:
        # TODO: Implement actual TikTok upload
        # TikTok upload requires a different flow (initiate upload, get URL, upload chunks)
        # For now, mark as failed with instructions
        error_msg = "TikTok upload not yet implemented. YouTube upload is available."
        logger.warning(f"[TikTok Upload] {error_msg}")
        upload.status = "failed"
        upload.error_message = error_msg
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=error_msg,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"TikTok upload failed: {str(e)}"
        logger.exception(f"[TikTok Upload] {error_msg}")
        upload.status = "failed"
        upload.error_message = error_msg
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )

    return upload


@upload_router.get("/", response_model=List[UploadResponse])
async def list_uploads(
    skip: int = 0,
    limit: int = 100,
    platform: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List all uploads with optional platform filter."""
    query = db.query(Upload)
    if platform:
        query = query.filter(Upload.platform == platform)

    uploads = query.offset(skip).limit(limit).all()
    return uploads


@upload_router.get("/{upload_id}/status", response_model=UploadResponse)
async def get_upload_status(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Check the status of a specific upload."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    return upload


@upload_router.get("/{upload_id}/logs")
async def get_upload_logs(
    upload_id: int,
    lines: int = 50,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get server logs for a specific upload to help debug issues."""
    import glob
    
    # Find the most recent log file
    log_files = glob.glob("/tmp/vms.log*") + glob.glob("vms.log*") + glob.glob("*.log")
    
    if not log_files:
        return {"upload_id": upload_id, "logs": "No log files found"}
    
    # Sort by modification time (most recent first)
    log_files.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0, reverse=True)
    
    logs = []
    keywords = [f"upload_id={upload_id}", f"upload_id={upload_id}"]
    
    for log_file in log_files[:3]:  # Check up to 3 most recent log files
        try:
            with open(log_file, 'r') as f:
                file_logs = f.readlines()
                # Filter lines related to this upload
                for line in file_logs:
                    if any(kw in line for kw in keywords) or "[YouTube Upload]" in line or "[TikTok Upload]" in line:
                        logs.append(line.strip())
        except Exception as e:
            logger.error(f"Error reading log file {log_file}: {e}")
    
    # Return last N lines
    logs = logs[-lines:] if len(logs) > lines else logs
    
    return {
        "upload_id": upload_id,
        "log_file": log_files[0] if log_files else None,
        "log_count": len(logs),
        "logs": logs,
    }


app.include_router(upload_router)


# =============================================================================
# Analytics Routes
# =============================================================================

analytics_router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@analytics_router.get("/", response_model=AnalyticsResponse)
async def get_analytics_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get analytics dashboard data."""
    # Aggregate statistics
    total_uploads = db.query(Upload).count()
    total_views = db.query(VideoAnalytics).with_entities(
        VideoAnalytics.views
    ).count()
    total_likes = db.query(VideoAnalytics).with_entities(
        VideoAnalytics.likes
    ).count()
    total_comments = db.query(VideoAnalytics).with_entities(
        VideoAnalytics.comments
    ).count()

    # Platform breakdown
    platform_stats = {}
    for platform in ["youtube", "tiktok"]:
        uploads = db.query(Upload).filter(Upload.platform == platform).count()
        platform_stats[platform] = {
            "uploads": uploads,
            "views": 0,  # TODO: Aggregate views per platform
            "likes": 0,
            "comments": 0,
        }

    # Recent uploads
    recent = (
        db.query(Upload)
        .order_by(Upload.uploaded_at.desc())
        .limit(10)
        .all()
    )
    recent_uploads = [
        {
            "id": u.id,
            "platform": u.platform,
            "title": u.title,
            "status": u.status,
            "uploaded_at": u.uploaded_at,
        }
        for u in recent
    ]

    return {
        "total_uploads": total_uploads,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "platform_breakdown": platform_stats,
        "recent_uploads": recent_uploads,
    }


@analytics_router.get("/{upload_id}", response_model=List[UploadAnalyticsResponse])
async def get_upload_analytics(
    upload_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Get analytics for a specific upload."""
    upload = db.query(Upload).filter(Upload.id == upload_id).first()
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    analytics = (
        db.query(VideoAnalytics)
        .filter(VideoAnalytics.upload_id == upload_id)
        .order_by(VideoAnalytics.collected_at.desc())
        .all()
    )

    return analytics


app.include_router(analytics_router)


# =============================================================================
# Printer Routes
# =============================================================================

printer_router = APIRouter(prefix="/api/printers", tags=["Printers"])


@printer_router.get("/", response_model=List[PrinterResponse])
async def list_printers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """List all configured printers."""
    printers = db.query(Printer).all()
    logger.info(f"Listing {len(printers)} configured printers")
    
    result = []
    for printer in printers:
        video_count = db.query(Video).filter(Video.printer_id == printer.id).count()
        logger.debug(f"Printer '{printer.name}': {video_count} videos, URL: {printer.moonraker_url}")
        result.append(
            {
                "id": printer.id,
                "name": printer.name,
                "moonraker_url": printer.moonraker_url,
                "api_key": printer.api_key,
                "is_active": printer.is_active,
                "created_at": printer.created_at,
                "video_count": video_count,
            }
        )
    return result


@printer_router.post("/", response_model=PrinterResponse, status_code=status.HTTP_201_CREATED)
async def add_printer(
    printer_data: PrinterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Add a new printer."""
    # Check if printer with same name exists
    existing = db.query(Printer).filter(Printer.name == printer_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Printer with this name already exists",
        )

    # Test connectivity before adding
    logger.info(f"Testing connectivity to printer at {printer_data.moonraker_url}")
    try:
        client = MoonrakerClient(
            base_url=printer_data.moonraker_url,
            api_key=printer_data.api_key,
        )
        is_connected = await client.connect()
        if not is_connected:
            logger.warning(f"Cannot connect to printer at {printer_data.moonraker_url}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot connect to Moonraker at {printer_data.moonraker_url}. Please check the URL and ensure the printer is online.",
            )
        logger.info(f"Successfully connected to printer at {printer_data.moonraker_url}")
    except Exception as e:
        logger.error(f"Error testing printer connectivity: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error connecting to printer: {str(e)}",
        )

    printer = Printer(
        name=printer_data.name,
        moonraker_url=printer_data.moonraker_url,
        api_key=printer_data.api_key,
    )

    db.add(printer)
    db.commit()
    db.refresh(printer)

    return {
        "id": printer.id,
        "name": printer.name,
        "moonraker_url": printer.moonraker_url,
        "api_key": printer.api_key,
        "is_active": printer.is_active,
        "created_at": printer.created_at,
        "video_count": 0,
    }


@printer_router.delete("/{printer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """Delete a printer and associated videos."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if printer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Printer not found",
        )

    # TODO: Handle cleanup of associated videos and files
    db.delete(printer)
    db.commit()

    return None


@printer_router.post("/{printer_id}/sync")
async def sync_printer_videos(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Sync videos from a printer."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if printer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Printer not found",
        )

    logger.info(f"Starting video sync for printer '{printer.name}' (ID: {printer_id})")

    try:
        client = MoonrakerClient(
            base_url=printer.moonraker_url,
            api_key=printer.api_key,
        )

        # Test connection first
        is_connected = await client.connect()
        if not is_connected:
            logger.error(f"Cannot connect to printer '{printer.name}' at {printer.moonraker_url}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Printer '{printer.name}' is not accessible. Please check if it's online.",
            )

        # Get timelapse files
        files = await client.get_timelapse_files()
        logger.info(f"Found {len(files)} timelapse files on printer '{printer.name}'")

        synced_count = 0
        for file_info in files:
            filename = file_info.get("path", file_info.get("filename", ""))
            if not filename:
                continue

            # Check if video already exists
            existing = db.query(Video).filter(
                Video.printer_id == printer.id,
                Video.filename == filename,
            ).first()

            if existing:
                logger.debug(f"Video '{filename}' already exists, skipping")
                continue

            # Create video record
            video = Video(
                printer_id=printer.id,
                filename=filename,
                original_path=f"{printer.moonraker_url}/server/files/timelapse/{filename}",
                size_bytes=file_info.get("size", 0),
                duration_seconds=0,  # Will be updated after download
                width=0,
                height=0,
                fps=0,
                moonraker_metadata_json=file_info,
            )
            db.add(video)
            synced_count += 1
            logger.info(f"Added video '{filename}' to database")

        db.commit()
        logger.info(f"Sync completed for printer '{printer.name}': {synced_count} new videos")

        return {
            "message": "Sync completed",
            "printer_id": printer_id,
            "printer_name": printer.name,
            "synced_videos": synced_count,
            "total_files_found": len(files),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error syncing videos for printer '{printer.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error syncing videos: {str(e)}",
        )


@app.get("/api/printers/{printer_id}/health")
async def printer_health_check(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Check if a printer is accessible."""
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if printer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Printer not found",
        )

    logger.info(f"Health check for printer '{printer.name}' at {printer.moonraker_url}")

    try:
        client = MoonrakerClient(
            base_url=printer.moonraker_url,
            api_key=printer.api_key,
        )

        is_connected = await client.connect()

        if is_connected:
            # Try to get server info for more details
            server_info = await client._request("GET", "/server/info")
            return {
                "printer_id": printer_id,
                "printer_name": printer.name,
                "status": "online",
                "moonraker_url": printer.moonraker_url,
                "server_info": server_info.get("result", {}) if server_info else {},
                "message": "Printer is accessible",
            }
        else:
            return {
                "printer_id": printer_id,
                "printer_name": printer.name,
                "status": "offline",
                "moonraker_url": printer.moonraker_url,
                "server_info": {},
                "message": "Cannot connect to printer",
            }

    except Exception as e:
        logger.error(f"Health check failed for printer '{printer.name}': {e}")
        return {
            "printer_id": printer_id,
            "printer_name": printer.name,
            "status": "error",
            "moonraker_url": printer.moonraker_url,
            "server_info": {},
            "message": f"Error: {str(e)}",
        }


@app.get("/api/printers/health/all")
async def all_printers_health_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Check health of all printers."""
    printers = db.query(Printer).all()
    results = []

    for printer in printers:
        try:
            client = MoonrakerClient(
                base_url=printer.moonraker_url,
                api_key=printer.api_key,
            )
            is_connected = await client.connect()

            results.append({
                "printer_id": printer.id,
                "printer_name": printer.name,
                "status": "online" if is_connected else "offline",
                "moonraker_url": printer.moonraker_url,
            })
        except Exception as e:
            logger.error(f"Health check failed for printer '{printer.name}': {e}")
            results.append({
                "printer_id": printer.id,
                "printer_name": printer.name,
                "status": "error",
                "moonraker_url": printer.moonraker_url,
                "error": str(e),
            })

    online_count = sum(1 for r in results if r["status"] == "online")

    return {
        "total_printers": len(printers),
        "online": online_count,
        "offline": len(printers) - online_count,
        "printers": results,
    }


app.include_router(printer_router)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "moonraker_url": settings.moonraker_url,
    }


@app.get("/api/printers/test-default")
async def test_default_printer(
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """Test connectivity to the default Moonraker URL from .env."""
    if not settings.moonraker_url or settings.moonraker_url == "http://your-printer-ip:4409":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No default Moonraker URL configured. Set MOONRAKER_URL in your .env file.",
        )

    logger.info(f"Testing default Moonraker connection: {settings.moonraker_url}")

    try:
        client = MoonrakerClient(
            base_url=settings.moonraker_url,
            api_key=settings.moonraker_api_key,
        )

        is_connected = await client.connect()

        if is_connected:
            # Get server info
            server_info = await client._request("GET", "/server/info")
            # Get timelapse files
            timelapse_files = await client.get_timelapse_files()

            return {
                "status": "online",
                "moonraker_url": settings.moonraker_url,
                "message": "Successfully connected to Moonraker",
                "server_info": server_info.get("result", {}) if server_info else {},
                "timelapse_files_count": len(timelapse_files),
                "sample_files": timelapse_files[:5] if timelapse_files else [],
            }
        else:
            return {
                "status": "offline",
                "moonraker_url": settings.moonraker_url,
                "message": "Cannot connect to Moonraker. Check if printer is online.",
            }

    except Exception as e:
        logger.error(f"Error testing default Moonraker: {e}")
        return {
            "status": "error",
            "moonraker_url": settings.moonraker_url,
            "message": f"Error: {str(e)}",
        }


# =============================================================================
# Startup Event
# =============================================================================

@app.on_event("startup")
async def startup_event() -> None:
    """Initialize database and create admin user on startup."""
    from database import init_db, SessionLocal
    from database.crud import create_user, get_user_by_username
    init_db()
    
    logger.info("=" * 60)
    logger.info("Video Management System Starting")
    logger.info("=" * 60)
    logger.info(f"Default Moonraker URL: {settings.moonraker_url}")
    logger.info(f"Database URL: {settings.database_url}")
    logger.info(f"Registration allowed: {settings.allow_registration}")
    logger.info("=" * 60)
    
    # Test default Moonraker connection
    if settings.moonraker_url and settings.moonraker_url != "http://your-printer-ip:4409":
        logger.info(f"Testing default Moonraker connection at {settings.moonraker_url}")
        try:
            client = MoonrakerClient(
                base_url=settings.moonraker_url,
                api_key=settings.moonraker_api_key,
            )
            is_connected = await client.connect()
            if is_connected:
                logger.info("✅ Default Moonraker printer is ONLINE and accessible")
            else:
                logger.warning("❌ Default Moonraker printer is OFFLINE or not accessible")
                logger.warning(f"   URL: {settings.moonraker_url}")
                logger.warning("   Please check your printer is powered on and Moonraker is running")
        except Exception as e:
            logger.error(f"❌ Error connecting to default Moonraker: {e}")
    else:
        logger.warning("⚠️  No default Moonraker URL configured")
        logger.warning("   Set MOONRAKER_URL in your .env file")
    
    # Create admin user from environment variables if configured
    if settings.admin_username and settings.admin_password:
        db = SessionLocal()
        try:
            existing_user = get_user_by_username(db, settings.admin_username)
            if not existing_user:
                # Truncate password to 72 bytes (bcrypt limit)
                admin_password = settings.admin_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
                admin_user = create_user(
                    db,
                    username=settings.admin_username,
                    password_hash=get_password_hash(admin_password),
                    email=None,
                )
                logger.info(f"Admin user '{settings.admin_username}' created from environment variables")
            else:
                logger.info(f"Admin user '{settings.admin_username}' already exists")
        except Exception as e:
            logger.error(f"Failed to create admin user: {e}")
        finally:
            db.close()
