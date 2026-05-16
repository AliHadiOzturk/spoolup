"""Upload queue manager."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Upload

logger = logging.getLogger(__name__)


class UploadManager:
    """Manages the upload queue."""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    def queue_upload(self, upload_id: int) -> bool:
        """Add an upload to the queue."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload:
                logger.error(f"Upload {upload_id} not found")
                return False
            if upload.status in ("queued", "uploading", "platform_processing"):
                logger.warning(f"Upload {upload_id} already in queue")
                return False
            upload.status = "queued"
            db.commit()
            logger.info(f"Upload {upload_id} queued")
            return True
        finally:
            db.close()

    def get_queue_status(self) -> dict:
        """Return current queue status (queued, active, completed, failed counts)."""
        db = self.db_session_factory()
        try:
            return {
                "queued": db.query(Upload).filter(Upload.status == "queued").count(),
                "active": db.query(Upload).filter(Upload.status.in_(("uploading", "platform_processing"))).count(),
                "completed": db.query(Upload).filter(Upload.status == "completed").count(),
                "failed": db.query(Upload).filter(Upload.status == "failed").count(),
                "cancelled": db.query(Upload).filter(Upload.status == "cancelled").count(),
                "pending": db.query(Upload).filter(Upload.status == "pending").count(),
            }
        finally:
            db.close()

    def cancel_upload(self, upload_id: int) -> bool:
        """Cancel a pending upload."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload:
                logger.error(f"Upload {upload_id} not found")
                return False
            if upload.status in ("completed", "cancelled"):
                logger.warning(f"Upload {upload_id} cannot be cancelled (status: {upload.status})")
                return False
            upload.status = "cancelled"
            db.commit()
            logger.info(f"Upload {upload_id} cancelled")
            return True
        finally:
            db.close()

    def retry_upload(self, upload_id: int) -> bool:
        """Retry a failed upload."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload:
                logger.error(f"Upload {upload_id} not found")
                return False
            if upload.status != "failed":
                logger.warning(f"Upload {upload_id} is not failed (status: {upload.status})")
                return False
            upload.status = "queued"
            upload.retry_count = 0
            upload.error_message = None
            upload.error_code = None
            db.commit()
            logger.info(f"Upload {upload_id} queued for retry")
            return True
        finally:
            db.close()
