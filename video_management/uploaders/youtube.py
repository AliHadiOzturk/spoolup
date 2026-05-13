#!/usr/bin/env python3
"""
YouTube Data API v3 uploader for video management system.

Provides OAuth2 authentication, video upload, status checking,
analytics retrieval, metadata updates, and quota tracking.
Supports YouTube Shorts (max 60s, 9:16 aspect ratio, #Shorts in title).
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
]

# YouTube API quota costs
QUOTA_COSTS = {
    "videos.insert": 1600,
    "videos.list": 1,
    "videos.update": 50,
    "videos.getRating": 1,
    "channels.list": 1,
    "search.list": 100,
}

# YouTube category IDs (common ones)
CATEGORY_IDS = {
    "film_and_animation": "1",
    "autos_and_vehicles": "2",
    "music": "10",
    "pets_and_animals": "15",
    "sports": "17",
    "travel_and_events": "19",
    "gaming": "20",
    "people_and_blogs": "22",
    "comedy": "23",
    "entertainment": "24",
    "news_and_politics": "25",
    "howto_and_style": "26",
    "education": "27",
    "science_and_technology": "28",
    "nonprofits_and_activism": "29",
}


class QuotaTracker:
    """Tracks YouTube API quota usage."""

    def __init__(self, daily_limit: int = 10000):
        self.daily_limit = daily_limit
        self.used = 0
        self.operations: List[Dict[str, Any]] = []

    def record(self, operation: str, cost: int) -> None:
        """Record quota usage for an operation."""
        self.used += cost
        self.operations.append({"operation": operation, "cost": cost})
        logger.info(f"Quota used: {cost} for {operation} (total: {self.used}/{self.daily_limit})")

    def get_remaining(self) -> int:
        """Get remaining quota for the day."""
        return max(0, self.daily_limit - self.used)

    def is_exceeded(self) -> bool:
        """Check if quota has been exceeded."""
        return self.used >= self.daily_limit

    def reset(self) -> None:
        """Reset quota tracking (call at midnight UTC)."""
        self.used = 0
        self.operations.clear()
        logger.info("Quota tracking reset")

    def get_summary(self) -> Dict[str, Any]:
        """Get quota usage summary."""
        return {
            "daily_limit": self.daily_limit,
            "used": self.used,
            "remaining": self.get_remaining(),
            "operations": self.operations,
        }


class YouTubeUploader:
    """YouTube Data API v3 uploader with OAuth2 authentication."""

    def __init__(self, quota_limit: int = 10000):
        self.credentials: Optional[Credentials] = None
        self.service: Optional[Any] = None
        self.token_path: Optional[str] = None
        self.quota_tracker = QuotaTracker(daily_limit=quota_limit)

    def authenticate(
        self,
        client_secrets_path: str,
        token_path: str = "youtube_token.json",
    ) -> bool:
        """Authenticate with YouTube using OAuth2 flow.

        Args:
            client_secrets_path: Path to client secrets JSON file.
            token_path: Path to save/load authentication token.

        Returns:
            True if authentication successful, False otherwise.
        """
        self.token_path = token_path

        # Check if token already exists
        if os.path.exists(token_path):
            logger.info(f"Loading existing token from {token_path}")
            try:
                with open(token_path, "r") as f:
                    token_data = json.load(f)

                self.credentials = Credentials.from_authorized_user_info(token_data, SCOPES)

                if self.credentials and self.credentials.valid:
                    self.service = build("youtube", "v3", credentials=self.credentials)
                    logger.info("Authentication successful using existing token")
                    return True

                # Refresh if expired
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    logger.info("Token expired, refreshing...")
                    from google.auth.transport.requests import Request
                    self.credentials.refresh(Request())
                    self._save_token()
                    self.service = build("youtube", "v3", credentials=self.credentials)
                    logger.info("Token refreshed successfully")
                    return True

            except Exception as e:
                logger.warning(f"Failed to load existing token: {e}")

        # Run OAuth flow if no valid token
        if not os.path.exists(client_secrets_path):
            logger.error(f"Client secrets file not found: {client_secrets_path}")
            return False

        try:
            logger.info("Starting OAuth2 flow...")
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            self.credentials = flow.run_local_server(port=0)
            self.service = build("youtube", "v3", credentials=self.credentials)
            self._save_token()
            logger.info("OAuth2 authentication successful")
            return True

        except Exception as e:
            logger.error(f"OAuth2 authentication failed: {e}")
            return False

    def _save_token(self) -> None:
        """Save credentials to token file."""
        if not self.credentials or not self.token_path:
            return

        try:
            token_dir = os.path.dirname(self.token_path)
            if token_dir and not os.path.exists(token_dir):
                os.makedirs(token_dir)

            with open(self.token_path, "w") as f:
                f.write(self.credentials.to_json())

            logger.info(f"Token saved to {self.token_path}")

        except Exception as e:
            logger.error(f"Failed to save token: {e}")

    def _check_service(self) -> bool:
        """Check if YouTube service is initialized."""
        if not self.service:
            logger.error("YouTube service not initialized. Call authenticate() first.")
            return False
        return True

    def _check_quota(self, operation: str) -> bool:
        """Check if enough quota remains for operation."""
        cost = QUOTA_COSTS.get(operation, 1)
        if self.quota_tracker.get_remaining() < cost:
            logger.error(f"Quota exceeded. Need {cost}, have {self.quota_tracker.get_remaining()}")
            return False
        return True

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category_id: str = "22",
        privacy_status: str = "private",
    ) -> Optional[str]:
        """Upload a video to YouTube.

        Args:
            video_path: Path to video file.
            title: Video title.
            description: Video description.
            tags: List of tags.
            category_id: YouTube category ID.
            privacy_status: Privacy status (private, unlisted, public).

        Returns:
            Video ID if upload successful, None otherwise.
        """
        if not self._check_service():
            return None

        if not self._check_quota("videos.insert"):
            return None

        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return None

        try:
            # Check if this is a Short
            is_short = self._is_short(video_path, title)
            if is_short and "#Shorts" not in title:
                title = f"{title} #Shorts"
                logger.info("Detected YouTube Shorts format, added #Shorts to title")

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                    "categoryId": category_id,
                },
                "status": {
                    "privacyStatus": privacy_status,
                },
            }

            media = MediaFileUpload(
                video_path,
                resumable=True,
            )

            logger.info(f"Uploading video: {title}")
            request = self.service.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response["id"]
            self.quota_tracker.record("videos.insert", QUOTA_COSTS["videos.insert"])
            logger.info(f"Upload complete. Video ID: {video_id}")

            return video_id

        except HttpError as e:
            logger.error(f"Upload failed: {e.resp.status} - {e._get_reason()}")
            return None
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return None

    def _is_short(self, video_path: str, title: str) -> bool:
        """Check if video qualifies as a YouTube Short.

        Shorts requirements:
        - Maximum 60 seconds duration
        - Aspect ratio 9:16 (or 1:1 for square)
        """
        try:
            import subprocess

            # Get video duration using ffprobe
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                duration = float(result.stdout.strip())
                if duration > 60:
                    return False

            # Get video dimensions
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                width, height = result.stdout.strip().split("x")
                width = int(width)
                height = int(height)

                # Check aspect ratio (9:16 or square)
                ratio = height / width if width > 0 else 0
                if ratio >= 1.0:
                    return True

        except FileNotFoundError:
            logger.warning("ffprobe not found. Install ffmpeg to detect Shorts format.")
        except Exception as e:
            logger.warning(f"Could not detect Shorts format: {e}")

        return False

    def check_upload_status(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Check video processing status.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dict with status info, or None if failed.
        """
        if not self._check_service():
            return None

        if not self._check_quota("videos.list"):
            return None

        try:
            response = self.service.videos().list(
                part="status,processingDetails",
                id=video_id,
            ).execute()

            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"])

            if not response.get("items"):
                logger.warning(f"Video not found: {video_id}")
                return None

            video = response["items"][0]
            status = video.get("status", {})
            processing = video.get("processingDetails", {})

            result = {
                "video_id": video_id,
                "upload_status": status.get("uploadStatus"),
                "privacy_status": status.get("privacyStatus"),
                "embeddable": status.get("embeddable"),
                "license": status.get("license"),
                "processing_status": processing.get("processingStatus"),
                "processing_progress": processing.get("processingProgress", {}),
            }

            logger.info(f"Video {video_id} status: {result['upload_status']}")
            return result

        except HttpError as e:
            logger.error(f"Status check failed: {e.resp.status} - {e._get_reason()}")
            return None
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return None

    def get_video_analytics(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video analytics (view count, likes, comments).

        Args:
            video_id: YouTube video ID.

        Returns:
            Dict with analytics data, or None if failed.
        """
        if not self._check_service():
            return None

        if not self._check_quota("videos.list"):
            return None

        try:
            response = self.service.videos().list(
                part="statistics",
                id=video_id,
            ).execute()

            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"])

            if not response.get("items"):
                logger.warning(f"Video not found: {video_id}")
                return None

            stats = response["items"][0].get("statistics", {})

            result = {
                "video_id": video_id,
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "favorite_count": int(stats.get("favoriteCount", 0)),
            }

            logger.info(
                f"Video {video_id} analytics: "
                f"{result['view_count']} views, "
                f"{result['like_count']} likes, "
                f"{result['comment_count']} comments"
            )
            return result

        except HttpError as e:
            logger.error(f"Analytics retrieval failed: {e.resp.status} - {e._get_reason()}")
            return None
        except Exception as e:
            logger.error(f"Analytics retrieval failed: {e}")
            return None

    def update_video_metadata(
        self,
        video_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Update video metadata.

        Args:
            video_id: YouTube video ID.
            title: New title (optional).
            description: New description (optional).
            tags: New tags (optional).

        Returns:
            True if update successful, False otherwise.
        """
        if not self._check_service():
            return False

        if not self._check_quota("videos.update"):
            return False

        try:
            # Get current video data
            response = self.service.videos().list(
                part="snippet",
                id=video_id,
            ).execute()

            if not response.get("items"):
                logger.warning(f"Video not found: {video_id}")
                return False

            video = response["items"][0]
            snippet = video["snippet"]

            # Update fields if provided
            if title is not None:
                snippet["title"] = title
            if description is not None:
                snippet["description"] = description
            if tags is not None:
                snippet["tags"] = tags

            body = {
                "id": video_id,
                "snippet": snippet,
            }

            self.service.videos().update(
                part="snippet",
                body=body,
            ).execute()

            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"])
            logger.info(f"Updated metadata for video {video_id}")
            return True

        except HttpError as e:
            logger.error(f"Metadata update failed: {e.resp.status} - {e._get_reason()}")
            return False
        except Exception as e:
            logger.error(f"Metadata update failed: {e}")
            return False

    def get_quota_summary(self) -> Dict[str, Any]:
        """Get quota usage summary.

        Returns:
            Dict with quota information.
        """
        return self.quota_tracker.get_summary()

    def get_category_id(self, category_name: str) -> str:
        """Get YouTube category ID by name.

        Args:
            category_name: Category name (e.g., 'gaming', 'education').

        Returns:
            Category ID string.
        """
        return CATEGORY_IDS.get(category_name.lower(), "22")
