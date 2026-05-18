"""
Scheduler for midnight analytics sync and other periodic tasks.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from analytics.collector import AnalyticsCollector
from database import get_db, SessionLocal
from uploaders.youtube import YouTubeUploader
from uploaders.tiktok import TikTokUploader
from upload_queue.scheduler import UploadScheduler as UploadQueueScheduler

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Manages scheduled tasks for the video management system."""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.analytics_collector: Optional[AnalyticsCollector] = None
        self.upload_scheduler: Optional[UploadQueueScheduler] = None
        self._init_collectors()
    
    def _init_collectors(self):
        """Initialize analytics collectors with uploaders."""
        try:
            db = next(get_db())
            youtube = None
            tiktok = None
            
            # Initialize YouTube uploader if credentials exist
            if settings.youtube_client_secrets:
                youtube = YouTubeUploader()
                youtube.authenticate(
                    settings.youtube_client_secrets,
                    settings.youtube_token_file,
                )
            
            # Initialize TikTok uploader if credentials exist
            if settings.tiktok_client_key and settings.tiktok_client_secret:
                tiktok = TikTokUploader(
                    settings.tiktok_client_key,
                    settings.tiktok_client_secret,
                )
            
            self.analytics_collector = AnalyticsCollector(db, youtube, tiktok)
            self.upload_scheduler = UploadQueueScheduler(SessionLocal)
            logger.info("Analytics collectors initialized")
        except Exception as e:
            logger.error(f"Failed to initialize analytics collectors: {e}")
    
    def _sync_analytics(self):
        """Sync analytics for all active uploads."""
        if not self.analytics_collector:
            logger.warning("Analytics collector not initialized, skipping sync")
            return
        
        logger.info(f"Starting scheduled analytics sync at {datetime.now()}")
        try:
            results = self.analytics_collector.sync_all_analytics()
            logger.info(f"Analytics sync completed: {results}")
        except Exception as e:
            logger.exception(f"Analytics sync failed: {e}")
    
    def _refresh_tokens(self):
        """Refresh OAuth tokens before expiry."""
        logger.info("Starting token refresh job")
        try:
            # Refresh YouTube tokens
            if settings.youtube_client_secrets and os.path.exists(settings.youtube_token_file):
                uploader = YouTubeUploader()
                uploader.authenticate(settings.youtube_client_secrets, settings.youtube_token_file)
                logger.info("YouTube tokens refreshed")
            
            # Refresh TikTok tokens
            if settings.tiktok_client_key and settings.tiktok_client_secret and os.path.exists(settings.tiktok_token_file):
                tiktok = TikTokUploader(
                    settings.tiktok_client_key,
                    settings.tiktok_client_secret,
                )
                tiktok.token_path = settings.tiktok_token_file
                if tiktok.is_authenticated() and tiktok.refresh_token():
                    logger.info("TikTok tokens refreshed")
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
    
    def _cleanup_old_files(self):
        """Clean up old raw files and temp files."""
        logger.info("Starting cleanup job")
        try:
            import shutil
            from pathlib import Path
            
            raw_dir = Path("uploads/raw")
            if raw_dir.exists():
                # Remove raw files older than 7 days that have been processed
                cutoff = datetime.now().timestamp() - (7 * 24 * 3600)
                removed = 0
                for file_path in raw_dir.glob("*"):
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                        file_path.unlink()
                        removed += 1
                logger.info(f"Cleanup removed {removed} old raw files")
        except Exception as e:
            logger.error(f"Cleanup job failed: {e}")
    
    def _check_scheduled_uploads(self):
        """Check for scheduled uploads that are due."""
        if self.upload_scheduler:
            try:
                self.upload_scheduler.check_scheduled_uploads()
            except Exception as e:
                logger.error(f"Scheduled upload check failed: {e}")
    
    def start(self):
        """Start the scheduler with all jobs."""
        # Analytics sync - daily at midnight
        self.scheduler.add_job(
            self._sync_analytics,
            trigger=CronTrigger(
                hour=settings.analytics_sync_hour,
                minute=settings.analytics_sync_minute,
            ),
            id="midnight_analytics_sync",
            name="Midnight Analytics Sync",
            replace_existing=True,
        )
        
        # Token refresh - daily at 3 AM
        self.scheduler.add_job(
            self._refresh_tokens,
            trigger=CronTrigger(hour=3, minute=0),
            id="token_refresh",
            name="OAuth Token Refresh",
            replace_existing=True,
        )
        
        # Cleanup - weekly on Sunday at 4 AM
        self.scheduler.add_job(
            self._cleanup_old_files,
            trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
            id="cleanup_old_files",
            name="Weekly Cleanup",
            replace_existing=True,
        )
        
        # Check scheduled uploads - every minute
        self.scheduler.add_job(
            self._check_scheduled_uploads,
            trigger=IntervalTrigger(minutes=1),
            id="check_scheduled_uploads",
            name="Check Scheduled Uploads",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info(
            f"Scheduler started with {len(self.scheduler.get_jobs())} jobs"
        )
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")


# Global scheduler instance
scheduler = TaskScheduler()
