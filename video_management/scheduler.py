"""
Scheduler for midnight analytics sync and other periodic tasks.
"""

import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from analytics.collector import AnalyticsCollector
from database import get_db
from uploaders.youtube import YouTubeUploader
from uploaders.tiktok import TikTokUploader

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Manages scheduled tasks for the video management system."""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.analytics_collector: Optional[AnalyticsCollector] = None
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
    
    def start(self):
        """Start the scheduler."""
        # Schedule midnight analytics sync
        trigger = CronTrigger(
            hour=settings.analytics_sync_hour,
            minute=settings.analytics_sync_minute,
        )
        self.scheduler.add_job(
            self._sync_analytics,
            trigger=trigger,
            id="midnight_analytics_sync",
            name="Midnight Analytics Sync",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info(
            f"Scheduler started. Analytics sync scheduled for "
            f"{settings.analytics_sync_hour:02d}:{settings.analytics_sync_minute:02d}"
        )
    
    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")


# Global scheduler instance
scheduler = TaskScheduler()