from pydantic_settings import BaseSettings
from typing import Optional
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
    
    # Security
    allow_registration: bool = False  # Set to true to allow public registration
    admin_username: Optional[str] = None  # Auto-create admin on startup
    admin_password: Optional[str] = None  # Required if admin_username is set
    max_login_attempts: int = 5  # Failed attempts before temporary lock
    
    class Config:
        env_file = f"{BASE_DIR}/.env"


settings = Settings()