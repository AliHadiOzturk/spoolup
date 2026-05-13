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
from pathlib import Path

# Base directory is the directory containing this file
BASE_DIR = Path(__file__).parent

# Ensure BASE_DIR is in path for imports
sys.path.insert(0, str(BASE_DIR))

from config import settings
from database import init_db
from ui.main import app

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Initialize and start the application."""
    # Ensure required directories exist (inside video_management/)
    os.makedirs(BASE_DIR / "data", exist_ok=True)
    os.makedirs(BASE_DIR / "logs", exist_ok=True)
    os.makedirs(BASE_DIR / "uploads" / "raw", exist_ok=True)
    os.makedirs(BASE_DIR / "uploads" / "processed", exist_ok=True)
    
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    
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