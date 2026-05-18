"""Upload queue worker."""

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from database.models import Upload
from uploaders.tiktok import TikTokAPIError, TikTokUploader
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
        self._tiktok_uploader: Optional[TikTokUploader] = None

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
        """Handle TikTok upload using TikTokUploader."""
        if not self._tiktok_uploader:
            self._tiktok_uploader = TikTokUploader(
                client_key=settings.tiktok_client_key,
                client_secret=settings.tiktok_client_secret,
            )
            self._tiktok_uploader.token_path = settings.tiktok_token_file

        processed_video = upload.processed_video
        if not processed_video:
            raise Exception("No processed video associated with upload")

        # Authenticate
        if not self._tiktok_uploader.is_authenticated():
            logger.info("TikTok not authenticated, attempting to load token")
            if not self._tiktok_uploader.authenticate():
                raise Exception("TikTok authentication failed. Please authenticate first.")

        # Extract privacy and interaction settings from upload tags
        tags = upload.tags or {}
        privacy_status = tags.get("privacy_status", settings.tiktok_default_privacy)
        allow_comments = tags.get("allow_comments", True)
        allow_duet = tags.get("allow_duet", True)
        allow_stitch = tags.get("allow_stitch", True)

        logger.info(
            f"Starting TikTok upload #{upload.id}: {upload.title} "
            f"(privacy={privacy_status}, comments={allow_comments}, "
            f"duet={allow_duet}, stitch={allow_stitch}, tags={upload.tags})"
        )

        # Upload video
        try:
            publish_id = self._tiktok_uploader.upload_video(
                video_path=processed_video.processed_path,
                title=upload.title or processed_video.video.title or "Untitled",
                description=upload.description or "",
                privacy_status=privacy_status,
                allow_comments=allow_comments,
                allow_duet=allow_duet,
                allow_stitch=allow_stitch,
            )
        except TikTokAPIError as e:
            # Pass through detailed TikTok API errors
            raise Exception(str(e)) from e

        if not publish_id:
            raise Exception("TikTok upload failed: no publish_id returned")

        logger.info(f"TikTok upload initiated: publish_id={publish_id}")
        return publish_id

    def _poll_tiktok_status(self, upload: Upload) -> bool:
        """Poll TikTok for upload processing completion.

        Returns:
            True if processing is complete (success or failure), False to continue polling.
        """
        if not self._tiktok_uploader or not upload.platform_video_id:
            return True

        logger.info(f"Polling TikTok status for publish_id={upload.platform_video_id}")
        status_data = self._tiktok_uploader.check_upload_status(upload.platform_video_id)

        if not status_data:
            logger.warning("Failed to get TikTok status, will retry")
            return False

        platform_status = status_data.get("status")
        upload.platform_status = platform_status

        if platform_status == "PUBLISH_COMPLETE":
            logger.info(f"TikTok upload {upload.id} published successfully")
            return True
        elif platform_status in ("PUBLISH_FAILED", "FAILED"):
            fail_reason = status_data.get("fail_reason", "Unknown")
            logger.error(f"TikTok upload {upload.id} failed: {fail_reason}")
            upload.error_message = f"TikTok publishing failed: {fail_reason}"
            return True
        elif platform_status == "PROCESSING":
            logger.info(f"TikTok upload {upload.id} still processing")
            return False
        else:
            logger.warning(f"Unknown TikTok status: {platform_status}")
            return False

    def _poll_platform_status(self, upload_id: int):
        """Poll platform for processing completion."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload or upload.status != "platform_processing":
                return

            if upload.platform == "tiktok":
                # Poll TikTok with configurable interval and timeout
                poll_interval = settings.tiktok_poll_interval
                max_poll_time = settings.tiktok_max_poll_time
                total_waited = 0

                while total_waited < max_poll_time:
                    if self._stop_event.is_set():
                        logger.info(f"Worker stopping, aborting poll for upload {upload_id}")
                        return

                    # Refresh upload from DB to get latest state
                    db.refresh(upload)
                    if upload.status != "platform_processing":
                        return

                    is_complete = self._poll_tiktok_status(upload)
                    db.commit()

                    if is_complete:
                        if upload.error_message:
                            upload.status = "failed"
                        else:
                            upload.status = "completed"
                            upload.completed_at = datetime.utcnow()
                        db.commit()
                        logger.info(f"Upload {upload_id} marked as {upload.status}")
                        return

                    time.sleep(poll_interval)
                    total_waited += poll_interval

                # Max poll time exceeded
                logger.warning(f"Max poll time exceeded for upload {upload_id}")
                upload.status = "failed"
                upload.error_message = "Platform processing timeout"
                db.commit()

            else:
                # TODO: implement actual polling with YouTube API
                # For now, mark as completed after a short delay
                asyncio.run(asyncio.sleep(5))
                upload.status = "completed"
                upload.completed_at = datetime.utcnow()
                db.commit()
                logger.info(f"Upload {upload_id} marked as completed")
        finally:
            db.close()
