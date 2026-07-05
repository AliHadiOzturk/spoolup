"""
Video Management System for 3D Printer Timelapse Videos

Main application entry point that initializes all components
and starts the FastAPI web server.

Run from the video_management/ directory:
    source venv/bin/activate
    python main.py
"""

import logging
import os
import sys
import signal
from pathlib import Path

# Base directory is the directory containing this file
BASE_DIR = Path(__file__).parent

# Ensure BASE_DIR is in path for imports
sys.path.insert(0, str(BASE_DIR))

from config import settings
from database import init_db, run_migrations, dispose_engine, SessionLocal
from database.models import User
from ui.main import app
from scheduler import TaskScheduler
from upload_queue.worker import UploadWorker
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Global instances
upload_worker: UploadWorker = None
scheduler: TaskScheduler = None


def create_admin_user():
    """Create admin user from environment variables if configured."""
    if not settings.admin_username or not settings.admin_password:
        return
    
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.admin_username).first()
        if existing:
            logger.info(f"Admin user '{settings.admin_username}' already exists")
            return
        
        from auth import get_password_hash
        admin = User(
            username=settings.admin_username,
            password_hash=get_password_hash(settings.admin_password),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        logger.info(f"Admin user '{settings.admin_username}' created successfully")
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        db.rollback()
    finally:
        db.close()


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutdown signal received, stopping services...")
    
    if upload_worker:
        upload_worker.stop()
    
    if scheduler:
        scheduler.stop()
    
    dispose_engine()
    
    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    """Initialize and start the application."""
    # Setup logging first
    setup_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
        log_dir=str(BASE_DIR / "logs"),
        log_rotation_days=settings.log_rotation_days,
        enable_console=True,
    )
    
    # Ensure required directories exist (inside video_management/)
    for _dir in [
        BASE_DIR / "data",
        BASE_DIR / "logs",
        BASE_DIR / "uploads" / "raw",
        BASE_DIR / "uploads" / "processed",
    ]:
        os.makedirs(_dir, exist_ok=True, mode=0o700)
        try:
            os.chmod(_dir, 0o700)
        except OSError:
            pass
    
    # Initialize database (run migrations or create tables)
    logger.info("Initializing database...")
    run_migrations()

    # Restrict database file permissions in production
    db_file = BASE_DIR / "data" / "vms.db"
    if db_file.exists():
        try:
            os.chmod(db_file, 0o600)
            logger.info("Database file permissions set to 0o600")
        except OSError as e:
            logger.warning(f"Could not set database file permissions: {e}")

    # Create admin user if configured
    create_admin_user()

    if settings.debug:
        logger.warning(
            "DEBUG mode is enabled. This should NOT be used in production."
        )

    if not settings.debug:
        localhost_origins = [
            o for o in settings.cors_origins_list
            if "localhost" in o or "127.0.0.1" in o
        ]
        if localhost_origins:
            logger.warning(
                "CORS origins include localhost/127.0.0.1 in non-debug mode: %s. "
                "Update CORS_ORIGINS to your production domain.",
                localhost_origins,
            )
    
    # Start upload worker
    global upload_worker
    logger.info("Starting upload worker...")
    upload_worker = UploadWorker(SessionLocal)
    upload_worker.start()
    
    # Start scheduler
    global scheduler
    logger.info("Starting scheduler...")
    scheduler = TaskScheduler()
    scheduler.start()
    
    # Register shutdown handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start server
    import uvicorn
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "ui.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug",
    )


if __name__ == "__main__":
    main()
