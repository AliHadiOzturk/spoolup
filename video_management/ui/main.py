"""FastAPI web interface for the video management system with Vue.js SPA."""

import logging
import os
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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
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
    AudioTrack,
    Printer,
    ProcessedVideo,
    Upload,
    User,
    Video,
    VideoAnalytics,
    ZipArchive,
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


class PrinterResponse(BaseModel):
    id: int
    name: str
    moonraker_url: str
    api_key: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


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
    version="2.0.0"
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Vue SPA Serving
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_spa():
    """Serve the Vue SPA index.html."""
    index_path = VUE_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
        <head><title>VMS</title></head>
        <body>
            <h1>Video Management System</h1>
            <p>Vue frontend is not built yet. Run `npm run build` in the vue directory.</p>
        </body>
        </html>
        """
    )


@app.get("/{path:path}")
async def serve_spa_routes(path: str):
    """Serve Vue Router routes by returning index.html for non-API paths."""
    # Skip API routes
    if path.startswith("api/") or path.startswith("static/"):
        raise HTTPException(status_code=404)
    
    # Try to serve static files first
    file_path = VUE_DIST_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    
    # Fall back to index.html for client-side routing
    index_path = VUE_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    raise HTTPException(status_code=404)


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
async def login(form_data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current authenticated user information."""
    return current_user


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
    
    # Apply sorting
    if sort_by == "date":
        query = query.order_by(Video.created_at.desc())
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


@app.get("/api/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific video by ID."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@app.put("/api/videos/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: int,
    update: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update video metadata."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if update.title is not None:
        video.title = update.title
    if update.description is not None:
        video.description = update.description
    if update.tags is not None:
        video.tags = update.tags
    if update.category is not None:
        video.category = update.category
    
    video.modified_at = datetime.utcnow()
    db.commit()
    db.refresh(video)
    return video


# =============================================================================
# Upload Routes
# =============================================================================

@app.get("/api/uploads", response_model=List[UploadResponse])
async def list_uploads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all uploads."""
    uploads = db.query(Upload).order_by(Upload.created_at.desc()).all()
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
        videos = client.list_timelapse_videos()
        
        synced_count = 0
        for video_data in videos:
            # Check if video already exists
            existing = db.query(Video).filter(
                Video.original_path == video_data["path"]
            ).first()
            
            if not existing:
                video = Video(
                    printer_id=printer_id,
                    filename=video_data["name"],
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
    return {
        "youtube_connected": bool(settings.youtube_token_file and os.path.exists(settings.youtube_token_file)),
        "tiktok_connected": bool(settings.tiktok_token_file and os.path.exists(settings.tiktok_token_file)),
        "processing_defaults": {
            "resolution": settings.output_resolution,
            "max_duration": settings.max_video_duration,
            "crop_mode": settings.default_crop_mode
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)