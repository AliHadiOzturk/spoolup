from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional, List
import os
from pathlib import Path

# Base directory is the directory containing this file (video_management/)
BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    # Application
    app_name: str = "Video Management System"
    debug: bool = False
    secret_key: str = "your-secret-key-change-this"
    
    # Database (relative to video_management/)
    database_url: str = f"sqlite:///{BASE_DIR}/data/vms.db"
    
    # Moonraker
    moonraker_url: str = "http://192.168.1.115:4409"
    moonraker_api_key: Optional[str] = None
    
    # YouTube
    youtube_client_secrets: Optional[str] = None
    youtube_token_file: str = f"{BASE_DIR}/data/youtube_token.json"
    
    # TikTok
    tiktok_client_key: Optional[str] = None
    tiktok_client_secret: Optional[str] = None
    tiktok_token_file: str = f"{BASE_DIR}/data/tiktok_token.json"
    tiktok_redirect_uri: str = "http://localhost:8000/api/tiktok/auth/callback"
    tiktok_default_privacy: str = "private"  # Must be private for unaudited apps
    tiktok_poll_interval: int = 30  # seconds
    tiktok_max_poll_time: int = 600  # 10 minutes
    
    # Video Processing
    ffmpeg_path: str = "ffmpeg"
    max_video_duration: int = 60  # seconds for Shorts
    output_resolution: str = "1080x1920"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Analytics
    analytics_sync_hour: int = 0  # Midnight
    analytics_sync_minute: int = 0
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    # Security
    allow_registration: bool = False  # Set to true to allow public registration
    admin_username: Optional[str] = None  # Auto-create admin on startup
    admin_password: Optional[str] = None  # Required if admin_username is set
    max_login_attempts: int = 5  # Failed attempts before temporary lock
    
    # Feature Flags
    enable_tiktok_upload: bool = True
    enable_post_processing: bool = True
    enable_bulk_operations: bool = False
    
    # Upload Settings
    max_concurrent_uploads: int = 1
    max_upload_retries: int = 3
    upload_chunk_size: int = 5 * 1024 * 1024  # 5MB
    
    # Processing Defaults
    default_zoom_level: float = 0.1
    default_target_duration: int = 60
    default_crop_mode: str = "center"
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"
    log_rotation_days: int = 30
    
    class Config:
        env_file = f"{BASE_DIR}/.env"


settings = Settings()
