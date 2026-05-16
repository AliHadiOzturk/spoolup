"""Upload scheduler for future uploads."""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models import Upload

logger = logging.getLogger(__name__)


class UploadScheduler:
    """Schedules uploads for future times."""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    def schedule_upload(self, upload_id: int, scheduled_time: datetime) -> bool:
        """Schedule upload for future time."""
        db = self.db_session_factory()
        try:
            upload = db.query(Upload).filter(Upload.id == upload_id).first()
            if not upload:
                logger.error(f"Upload {upload_id} not found")
                return False
            if upload.status != "pending":
                logger.warning(f"Upload {upload_id} must be pending to schedule (status: {upload.status})")
                return False
            upload.scheduled_for = scheduled_time
            db.commit()
            logger.info(f"Upload {upload_id} scheduled for {scheduled_time}")
            return True
        finally:
            db.close()

    def check_scheduled_uploads(self):
        """Check if any scheduled uploads are due and queue them."""
        db = self.db_session_factory()
        try:
            now = datetime.utcnow()
            uploads = (
                db.query(Upload)
                .filter(
                    Upload.scheduled_for <= now,
                    Upload.status == "pending",
                )
                .all()
            )
            for upload in uploads:
                upload.status = "queued"
                upload.scheduled_for = None
                logger.info(f"Scheduled upload {upload.id} is now queued")
            db.commit()
            return len(uploads)
        finally:
            db.close()

    def get_scheduled_uploads(self) -> List[Upload]:
        """List all scheduled uploads."""
        db = self.db_session_factory()
        try:
            return (
                db.query(Upload)
                .filter(
                    Upload.scheduled_for.isnot(None),
                    Upload.status == "pending",
                )
                .order_by(Upload.scheduled_for)
                .all()
            )
        finally:
            db.close()
