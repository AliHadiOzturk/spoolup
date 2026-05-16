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

    def record(self, operation: str, cost: int, success: bool = True) -> None:
        """Record quota usage for an operation.

        Args:
            operation: API operation name.
            cost: Quota cost of the operation.
            success: Whether the request succeeded or failed.
        """
        self.used += cost
        self.operations.append({
            "operation": operation,
            "cost": cost,
            "success": success,
        })
        status = "succeeded" if success else "failed"
        logger.info(
            f"Quota used: {cost} for {operation} ({status}) "
            f"(total: {self.used}/{self.daily_limit})"
        )

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

    @classmethod
    def list_accounts(cls, data_dir: str = "data") -> List[str]:
        """List available YouTube account names from token files.

        Args:
            data_dir: Directory containing token files.

        Returns:
            List of account names (extracted from youtube_token_{name}.json filenames).
        """
        accounts = []
        if not os.path.exists(data_dir):
            return accounts

        for filename in os.listdir(data_dir):
            if filename.startswith("youtube_token_") and filename.endswith(".json"):
                account_name = filename[len("youtube_token_"): -len(".json")]
                accounts.append(account_name)

        return sorted(accounts)

    def authenticate(
        self,
        client_secrets_path: str,
        token_path: str = "youtube_token.json",
        account_name: Optional[str] = None,
    ) -> bool:
        """Authenticate with YouTube using OAuth2 flow.

        Args:
            client_secrets_path: Path to client secrets JSON file.
            token_path: Path to save/load authentication token.
            account_name: Optional account name for multi-account support.
                          If provided, token is stored at data/youtube_token_{account_name}.json

        Returns:
            True if authentication successful, False otherwise.
        """
        if account_name:
            token_path = f"data/youtube_token_{account_name}.json"

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
        thumbnail_path: Optional[str] = None,
        language: str = "en",
        license: str = "youtube",
        embeddable: bool = True,
        public_stats_viewable: bool = True,
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        """Upload a video to YouTube.

        Args:
            video_path: Path to video file.
            title: Video title.
            description: Video description.
            tags: List of tags.
            category_id: YouTube category ID.
            privacy_status: Privacy status (private, unlisted, public).
            thumbnail_path: Optional path to thumbnail image to auto-upload after video.
            language: Default language for the video (e.g., "en").
            license: Video license ("youtube" or "creativeCommon").
            embeddable: Whether the video can be embedded on other sites.
            public_stats_viewable: Whether video statistics are publicly viewable.

        Returns:
            Tuple of (success: bool, video_id: Optional[str], error: Optional[dict]).
        """
        if not self._check_service():
            return False, None, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        if not self._check_quota("videos.insert"):
            return False, None, {"code": "QUOTA_EXCEEDED", "message": "API quota exceeded"}

        if not os.path.exists(video_path):
            error = {"code": "FILE_NOT_FOUND", "message": f"Video file not found: {video_path}"}
            logger.error(error["message"])
            return False, None, error

        try:
            # Check if this is a Short
            is_short = self._is_short(video_path, title)

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags or [],
                    "categoryId": category_id,
                    "defaultLanguage": language,
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "license": license,
                    "embeddable": embeddable,
                    "publicStatsViewable": public_stats_viewable,
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
                upload_status, response = request.next_chunk()
                if upload_status:
                    logger.info(f"Upload progress: {int(upload_status.progress() * 100)}%")

            video_id = response["id"]
            self.quota_tracker.record("videos.insert", QUOTA_COSTS["videos.insert"], success=True)
            logger.info(f"Upload complete. Video ID: {video_id}")

            # Auto-upload thumbnail if provided
            if thumbnail_path and os.path.exists(thumbnail_path):
                thumb_success, thumb_error = self.upload_thumbnail(video_id, thumbnail_path)
                if not thumb_success:
                    logger.warning(f"Thumbnail upload failed: {thumb_error}")

            return True, video_id, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.insert", QUOTA_COSTS["videos.insert"], success=False)
            logger.error(f"Upload failed: {error_info['code']} - {error_info['message']}")
            return False, None, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("videos.insert", QUOTA_COSTS["videos.insert"], success=False)
            logger.error(f"Upload failed: {e}")
            return False, None, error

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
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"], success=False)
            logger.error(f"Status check failed: {error_info['code']} - {error_info['message']}")
            return None
        except Exception as e:
            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"], success=False)
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
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"], success=False)
            logger.error(f"Analytics retrieval failed: {error_info['code']} - {error_info['message']}")
            return None
        except Exception as e:
            self.quota_tracker.record("videos.list", QUOTA_COSTS["videos.list"], success=False)
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
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"], success=False)
            logger.error(f"Metadata update failed: {error_info['code']} - {error_info['message']}")
            return False
        except Exception as e:
            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"], success=False)
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

    def _parse_http_error(self, error: HttpError) -> dict:
        """Parse Google API HttpError into a structured dict.

        Args:
            error: HttpError from googleapiclient.

        Returns:
            Dict with 'code' and 'message' keys.
        """
        try:
            error_details = json.loads(error.content.decode())
            error_info = error_details.get("error", {})
            return {
                "code": error_info.get("code", error.resp.status),
                "message": error_info.get("message", error._get_reason()),
            }
        except Exception:
            return {
                "code": error.resp.status,
                "message": error._get_reason(),
            }

    def upload_thumbnail(self, video_id: str, thumbnail_path: str) -> tuple[bool, Optional[dict]]:
        """Upload a custom thumbnail for a video.

        Args:
            video_id: YouTube video ID.
            thumbnail_path: Path to thumbnail image file.

        Returns:
            Tuple of (success: bool, error: Optional[dict]).
        """
        if not self._check_service():
            return False, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        if not os.path.exists(thumbnail_path):
            return False, {"code": "FILE_NOT_FOUND", "message": f"Thumbnail not found: {thumbnail_path}"}

        try:
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path),
            ).execute()

            self.quota_tracker.record("thumbnails.set", 50, success=True)
            logger.info(f"Thumbnail uploaded for video {video_id}")
            return True, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("thumbnails.set", 50, success=False)
            logger.error(f"Thumbnail upload failed: {error_info['code']} - {error_info['message']}")
            return False, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("thumbnails.set", 50, success=False)
            logger.error(f"Thumbnail upload failed: {e}")
            return False, error

    def add_to_playlist(self, video_id: str, playlist_id: str) -> tuple[bool, Optional[dict]]:
        """Add a video to a playlist.

        Args:
            video_id: YouTube video ID.
            playlist_id: YouTube playlist ID.

        Returns:
            Tuple of (success: bool, error: Optional[dict]).
        """
        if not self._check_service():
            return False, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        try:
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                },
            }

            self.service.playlistItems().insert(
                part="snippet",
                body=body,
            ).execute()

            self.quota_tracker.record("playlistItems.insert", 50, success=True)
            logger.info(f"Video {video_id} added to playlist {playlist_id}")
            return True, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("playlistItems.insert", 50, success=False)
            logger.error(f"Add to playlist failed: {error_info['code']} - {error_info['message']}")
            return False, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("playlistItems.insert", 50, success=False)
            logger.error(f"Add to playlist failed: {e}")
            return False, error

    def set_end_screen(self, video_id: str, template_id: str) -> tuple[bool, Optional[dict]]:
        """Set an end screen for a video.

        Args:
            video_id: YouTube video ID.
            template_id: End screen template ID.

        Returns:
            Tuple of (success: bool, error: Optional[dict]).
        """
        logger.warning("set_end_screen is not yet implemented")
        return False, {"code": "NOT_IMPLEMENTED", "message": "End screen setting is not yet implemented"}

    def update_privacy_status(self, video_id: str, privacy_status: str) -> tuple[bool, Optional[dict]]:
        """Update the privacy status of a video.

        Args:
            video_id: YouTube video ID.
            privacy_status: New privacy status (private, unlisted, public).

        Returns:
            Tuple of (success: bool, error: Optional[dict]).
        """
        if not self._check_service():
            return False, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        if not self._check_quota("videos.update"):
            return False, {"code": "QUOTA_EXCEEDED", "message": "API quota exceeded"}

        try:
            body = {
                "id": video_id,
                "status": {
                    "privacyStatus": privacy_status,
                },
            }

            self.service.videos().update(
                part="status",
                body=body,
            ).execute()

            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"], success=True)
            logger.info(f"Updated privacy status for video {video_id} to {privacy_status}")
            return True, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"], success=False)
            logger.error(f"Privacy update failed: {error_info['code']} - {error_info['message']}")
            return False, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("videos.update", QUOTA_COSTS["videos.update"], success=False)
            logger.error(f"Privacy update failed: {e}")
            return False, error

    def delete_video(self, video_id: str) -> tuple[bool, Optional[dict]]:
        """Delete a video from YouTube.

        Args:
            video_id: YouTube video ID.

        Returns:
            Tuple of (success: bool, error: Optional[dict]).
        """
        if not self._check_service():
            return False, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        try:
            self.service.videos().delete(id=video_id).execute()

            self.quota_tracker.record("videos.delete", 50, success=True)
            logger.info(f"Video {video_id} deleted")
            return True, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("videos.delete", 50, success=False)
            logger.error(f"Delete failed: {error_info['code']} - {error_info['message']}")
            return False, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("videos.delete", 50, success=False)
            logger.error(f"Delete failed: {e}")
            return False, error

    def list_playlists(self) -> tuple[Optional[List[dict]], Optional[dict]]:
        """List the authenticated user's playlists.

        Returns:
            Tuple of (playlists: Optional[List[dict]], error: Optional[dict]).
        """
        if not self._check_service():
            return None, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        if not self._check_quota("playlists.list"):
            return None, {"code": "QUOTA_EXCEEDED", "message": "API quota exceeded"}

        try:
            playlists = []
            request = self.service.playlists().list(
                part="snippet,status",
                mine=True,
                maxResults=50,
            )

            while request:
                response = request.execute()
                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    status = item.get("status", {})
                    playlists.append({
                        "id": item["id"],
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "privacy_status": status.get("privacyStatus", "unknown"),
                    })
                request = self.service.playlists().list_next(request, response)

            self.quota_tracker.record("playlists.list", 1, success=True)
            logger.info(f"Listed {len(playlists)} playlists")
            return playlists, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("playlists.list", 1, success=False)
            logger.error(f"List playlists failed: {error_info['code']} - {error_info['message']}")
            return None, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("playlists.list", 1, success=False)
            logger.error(f"List playlists failed: {e}")
            return None, error

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> tuple[Optional[str], Optional[dict]]:
        """Create a new playlist.

        Args:
            title: Playlist title.
            description: Playlist description.
            privacy_status: Privacy status (private, unlisted, public).

        Returns:
            Tuple of (playlist_id: Optional[str], error: Optional[dict]).
        """
        if not self._check_service():
            return None, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                },
                "status": {
                    "privacyStatus": privacy_status,
                },
            }

            response = self.service.playlists().insert(
                part="snippet,status",
                body=body,
            ).execute()

            playlist_id = response["id"]
            self.quota_tracker.record("playlists.insert", 50, success=True)
            logger.info(f"Playlist created: {playlist_id}")
            return playlist_id, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("playlists.insert", 50, success=False)
            logger.error(f"Create playlist failed: {error_info['code']} - {error_info['message']}")
            return None, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("playlists.insert", 50, success=False)
            logger.error(f"Create playlist failed: {e}")
            return None, error

    def get_account_info(self) -> tuple[Optional[dict], Optional[dict]]:
        """Get information about the authenticated YouTube channel.

        Returns:
            Tuple of (info: Optional[dict], error: Optional[dict]).
            Info dict contains 'channel_title', 'subscriber_count', etc.
        """
        if not self._check_service():
            return None, {"code": "SERVICE_NOT_INITIALIZED", "message": "YouTube service not initialized"}

        if not self._check_quota("channels.list"):
            return None, {"code": "QUOTA_EXCEEDED", "message": "API quota exceeded"}

        try:
            response = self.service.channels().list(
                part="snippet,statistics",
                mine=True,
            ).execute()

            self.quota_tracker.record("channels.list", QUOTA_COSTS["channels.list"], success=True)

            if not response.get("items"):
                return None, {"code": "CHANNEL_NOT_FOUND", "message": "No channel found for authenticated user"}

            channel = response["items"][0]
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})

            info = {
                "channel_title": snippet.get("title", ""),
                "channel_id": channel.get("id", ""),
                "subscriber_count": int(stats.get("subscriberCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
            }

            logger.info(
                f"Channel: {info['channel_title']} - "
                f"{info['subscriber_count']} subscribers, "
                f"{info['video_count']} videos"
            )
            return info, None

        except HttpError as e:
            error_info = self._parse_http_error(e)
            self.quota_tracker.record("channels.list", QUOTA_COSTS["channels.list"], success=False)
            logger.error(f"Get account info failed: {error_info['code']} - {error_info['message']}")
            return None, error_info
        except Exception as e:
            error = {"code": "UNKNOWN_ERROR", "message": str(e)}
            self.quota_tracker.record("channels.list", QUOTA_COSTS["channels.list"], success=False)
            logger.error(f"Get account info failed: {e}")
            return None, error
