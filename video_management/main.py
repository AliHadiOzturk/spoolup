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
from ui.main import app
from scheduler import TaskScheduler
from upload_queue.worker import UploadWorker
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)

# Global instances
upload_worker: UploadWorker = None
scheduler: TaskScheduler = None


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
    os.makedirs(BASE_DIR / "data", exist_ok=True)
    os.makedirs(BASE_DIR / "logs", exist_ok=True)
    os.makedirs(BASE_DIR / "uploads" / "raw", exist_ok=True)
    os.makedirs(BASE_DIR / "uploads" / "processed", exist_ok=True)
    
    # Initialize database (run migrations or create tables)
    logger.info("Initializing database...")
    run_migrations()
    
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
