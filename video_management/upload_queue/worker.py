"""Upload queue worker."""

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Upload
from uploaders.youtube import YouTubeUploader

logger = logging.getLogger(__name__)


class UploadWorker:
    """Background worker for processing uploads."""

    def __init__(self, db_session_factory, max_concurrent: int = 1):
        self.db_session_factory = db_session_factory
        self.max_concurrent = max_concurrent
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._youtube_uploader: Optional[YouTubeUploader] = None

    def start(self):
        """Start the background worker loop."""
        if self._thread and self._thread.is_alive():
            logger.warning("Worker already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Upload worker started")

    def stop(self):
        """Stop the worker gracefully."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Upload worker stopped")

    def _run(self):
        """Main worker loop."""
        while not self._stop_event.is_set():
            db = self.db_session_factory()
            try:
                upload = (
                    db.query(Upload)
                    .filter(Upload.status == "queued")
                    .order_by(Upload.updated_at)
                    .first()
                )
                if upload:
                    self._process_upload(upload.id)
                else:
                    time.sleep(1)
            finally:
                db.close()

    def _process_upload(self, upload_id: int):
        """Process a single upload."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload or upload.status in ("cancelled", "completed"):
                return

            upload.status = "uploading"
            upload.upload_progress = 0
            db.commit()
            logger.info(f"Processing upload {upload_id}")

            try:
                if upload.platform == "youtube":
                    platform_video_id = self._upload_to_youtube(upload)
                elif upload.platform == "tiktok":
                    platform_video_id = self._upload_to_tiktok(upload)
                else:
                    raise ValueError(f"Unsupported platform: {upload.platform}")

                if platform_video_id:
                    upload.status = "platform_processing"
                    upload.platform_video_id = platform_video_id
                    upload.upload_progress = 100
                    db.commit()
                    logger.info(f"Upload {upload_id} complete, platform processing")

                    # Poll for completion
                    self._poll_platform_status(upload_id)
                else:
                    raise Exception("Upload returned no video ID")

            except Exception as e:
                logger.exception(f"Upload {upload_id} failed: {e}")
                upload.status = "failed"
                upload.error_message = str(e)
                upload.retry_count += 1
                db.commit()

                if upload.retry_count < 3:
                    backoff = 2 ** upload.retry_count
                    logger.info(f"Retrying upload {upload_id} in {backoff}s")
                    time.sleep(backoff)
                    upload.status = "queued"
                    db.commit()

        finally:
            db.close()

    def _upload_to_youtube(self, upload: Upload) -> Optional[str]:
        """Handle YouTube upload using existing YouTubeUploader class."""
        if not self._youtube_uploader:
            self._youtube_uploader = YouTubeUploader()
            # TODO: authenticate with stored credentials
            # For now, assume authenticate() has been called externally

        processed_video = upload.processed_video
        if not processed_video:
            raise Exception("No processed video associated with upload")

        # Simulated progress updates every 10%
        video_id = self._youtube_uploader.upload_video(
            video_path=processed_video.processed_path,
            title=upload.title or processed_video.video.title or "Untitled",
            description=upload.description or "",
            tags=upload.tags.get("tags", []) if upload.tags else [],
        )
        return video_id

    def _upload_to_tiktok(self, upload: Upload) -> Optional[str]:
        """Handle TikTok upload (placeholder for now)."""
        logger.info("TikTok upload not yet implemented")
        return None

    def _poll_platform_status(self, upload_id: int):
        """Poll platform for processing completion."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload or upload.status != "platform_processing":
                return

            # TODO: implement actual polling with YouTube API
            # For now, mark as completed after a short delay
            asyncio.run(asyncio.sleep(5))
            upload.status = "completed"
            upload.completed_at = datetime.utcnow()
            db.commit()
            logger.info(f"Upload {upload_id} marked as completed")
        finally:
            db.close()
