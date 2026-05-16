"""
TikTok Content Posting API uploader.

Provides chunked video upload, status polling, and analytics retrieval
via the TikTok for Developers API (v2).

Note: This is a best-effort implementation. TikTok API endpoints and
behaviors may change. Actual app credentials are required for production use.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class TikTokAPIError(Exception):
    """Raised when the TikTok API returns an error response."""

    def __init__(self, message: str, code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.response_data = response_data or {}

    def __str__(self) -> str:
        if self.code:
            return f"[TikTok API Error {self.code}] {super().__str__()}"
        return super().__str__()

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
OAUTH_CONNECT_URL = "https://open.tiktokapis.com/v2/platform/oauth/connect/"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
VIDEO_INIT_ENDPOINT = f"{TIKTOK_API_BASE}/post/publish/video/init/"
VIDEO_CREATE_ENDPOINT = f"{TIKTOK_API_BASE}/post/publish/video/create/"
VIDEO_STATUS_ENDPOINT = f"{TIKTOK_API_BASE}/post/publish/status/"
VIDEO_LIST_ENDPOINT = f"{TIKTOK_API_BASE}/video/list/"
VIDEO_QUERY_ENDPOINT = f"{TIKTOK_API_BASE}/video/query/"
USER_INFO_ENDPOINT = f"{TIKTOK_API_BASE}/user/info/"

# TikTok API constraints
MAX_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB
MIN_CHUNK_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_FILE_SIZE = 287_600_000        # 287.6 MB
MAX_DURATION_SECONDS = 600         # 10 minutes

PRIVACY_LEVELS = {
    "public": "PUBLIC_TO_EVERYONE",
    "mutual_follow_friends": "MUTUAL_FOLLOW_FRIENDS",
    "followers": "FOLLOWER_OF_CREATOR",
    "private": "SELF_ONLY",
}

DEFAULT_TOKEN_PATH = "data/tiktok_token.json"


def _retry_on_rate_limit(func):
    """Decorator to retry on 429 rate limit with exponential backoff."""

    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 2

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except requests.HTTPError as exc:
                if exc.response.status_code == 429:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Rate limited (429). Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    if attempt == max_retries - 1:
                        raise
                else:
                    raise

    return wrapper


class TikTokUploader:
    """Upload videos to TikTok using the Content Posting API."""

    def __init__(self, client_key: Optional[str] = None, client_secret: Optional[str] = None) -> None:
        """Initialize with optional TikTok app credentials.

        Args:
            client_key: TikTok app client key.
            client_secret: TikTok app client secret.
        """
        self.client_key = client_key
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self.token_path: str = DEFAULT_TOKEN_PATH

    def _load_token(self) -> bool:
        """Load token from file if it exists."""
        if not os.path.exists(self.token_path):
            return False

        try:
            with open(self.token_path, "r") as f:
                token_data = json.load(f)

            self._access_token = token_data.get("access_token")
            self._refresh_token = token_data.get("refresh_token")
            self._token_expires_at = token_data.get("expires_at", 0.0)

            if self._access_token and time.time() < self._token_expires_at - 60:
                logger.info("Loaded valid token from file")
                return True

            if self._access_token and time.time() >= self._token_expires_at - 60:
                logger.info("Token expired, will refresh")
                return self.refresh_token()

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load token: {e}")

        return False

    def _save_token(self) -> None:
        """Save token data to file."""
        if not self._access_token:
            return

        try:
            token_dir = os.path.dirname(self.token_path)
            if token_dir and not os.path.exists(token_dir):
                os.makedirs(token_dir)

            token_data = {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._token_expires_at,
                "client_key": self.client_key,
            }

            with open(self.token_path, "w") as f:
                json.dump(token_data, f, indent=2)

            logger.info(f"Token saved to {self.token_path}")

        except OSError as e:
            logger.error(f"Failed to save token: {e}")

    def is_authenticated(self) -> bool:
        """Check if a valid access token is available."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True

        if self._load_token():
            return True

        return False

    def authenticate(self, auth_code: Optional[str] = None) -> bool:
        """Authenticate with TikTok using OAuth2 flow.

        If auth_code is provided, exchanges it for access and refresh tokens.
        Otherwise, attempts to load existing tokens from file.

        Args:
            auth_code: OAuth2 authorization code from TikTok redirect.

        Returns:
            True if authentication successful, False otherwise.
        """
        if not self.client_key or not self.client_secret:
            logger.error("client_key and client_secret are required for authentication")
            return False

        # Try loading existing token first
        if not auth_code and self._load_token():
            return True

        if not auth_code:
            logger.info("No auth_code provided and no valid token found")
            logger.info(
                f"Visit this URL to authorize: "
                f"{OAUTH_CONNECT_URL}?client_key={self.client_key}&redirect_uri=REDIRECT_URI&scope=video.publish"
            )
            return False

        logger.info("Exchanging auth_code for access token")
        try:
            response = requests.post(
                TOKEN_ENDPOINT,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "code": auth_code,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Token request failed: {e}")
            return False

        error_code = data.get("error_code")
        if error_code:
            error_msg = data.get("description", "Unknown error")
            logger.error(f"Token API error {error_code}: {error_msg}")
            return False

        self._access_token = data.get("access_token")
        self._refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in

        if not self._access_token:
            logger.error("No access_token in response")
            return False

        self._save_token()
        logger.info(f"Authentication successful (token expires in {expires_in}s)")
        return True

    def refresh_token(self) -> bool:
        """Refresh access token using refresh_token.

        Returns:
            True if refresh successful, False otherwise.
        """
        if not self._refresh_token:
            logger.warning("No refresh token available")
            return False

        if not self.client_key or not self.client_secret:
            logger.error("client_key and client_secret are required for token refresh")
            return False

        logger.info("Refreshing access token")
        try:
            response = requests.post(
                TOKEN_ENDPOINT,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            return False

        error_code = data.get("error_code")
        if error_code:
            error_msg = data.get("description", "Unknown error")
            logger.error(f"Token refresh API error {error_code}: {error_msg}")
            return False

        self._access_token = data.get("access_token")
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in

        if not self._access_token:
            logger.error("No access_token in refresh response")
            return False

        self._save_token()
        logger.info(f"Token refreshed (expires in {expires_in}s)")
        return True

    def _get_auth_headers(self) -> Dict[str, str]:
        """Return headers with the current access token."""
        if not self._access_token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    @_retry_on_rate_limit
    def _init_video_upload(
        self,
        title: str,
        description: str,
        privacy_status: str,
        file_size: int,
        chunk_size: int,
        total_chunk_count: int,
        allow_comments: bool,
        allow_duet: bool,
        allow_stitch: bool,
    ) -> Optional[Dict[str, Any]]:
        """Initialize a video upload session.

        Args:
            title: Video title.
            description: Video description.
            privacy_status: One of the supported privacy levels.
            file_size: Total file size in bytes.
            chunk_size: Size of each chunk in bytes.
            total_chunk_count: Total number of chunks.
            allow_comments: Whether to allow comments.
            allow_duet: Whether to allow duets.
            allow_stitch: Whether to allow stitches.

        Returns:
            The API response containing publish_id and upload_url, or None on failure.
        """
        if privacy_status not in PRIVACY_LEVELS:
            logger.error(
                f"Invalid privacy_status '{privacy_status}'. "
                f"Must be one of: {', '.join(PRIVACY_LEVELS.keys())}"
            )
            return None

        body = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
            "title": title,
            "description": description,
            "privacy_level": PRIVACY_LEVELS[privacy_status],
            "disable_duet": not allow_duet,
            "disable_comment": not allow_comments,
            "disable_stitch": not allow_stitch,
        }

        logger.info(f"Initializing upload: {title} ({file_size} bytes, {total_chunk_count} chunks)")
        try:
            response = requests.post(
                VIDEO_INIT_ENDPOINT,
                headers=self._get_auth_headers(),
                json=body,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Upload init failed: {e}")
            return None

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Upload init API error {error_code}: {error_msg}")
            return None

        return data.get("data", {})

    @_retry_on_rate_limit
    def _upload_chunk(
        self,
        upload_url: str,
        chunk_data: bytes,
        chunk_index: int,
        total_chunks: int,
    ) -> bool:
        """Upload a single chunk.

        Args:
            upload_url: The URL returned by the init endpoint.
            chunk_data: The chunk bytes.
            chunk_index: Zero-based chunk index.
            total_chunks: Total number of chunks.

        Returns:
            True if successful, False otherwise.
        """
        start_byte = chunk_index * len(chunk_data)
        end_byte = start_byte + len(chunk_data) - 1
        content_range = f"bytes {start_byte}-{end_byte}/{total_chunks * len(chunk_data)}"

        logger.info(f"Uploading chunk {chunk_index + 1}/{total_chunks} ({len(chunk_data)} bytes)")
        try:
            response = requests.put(
                upload_url,
                data=chunk_data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": content_range,
                },
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Chunk {chunk_index + 1} upload failed: {e}")
            return False

        logger.info(f"Chunk {chunk_index + 1}/{total_chunks} uploaded successfully")
        return True

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        privacy_status: str = "public",
        allow_comments: bool = True,
        allow_duet: bool = True,
        allow_stitch: bool = True,
    ) -> Optional[str]:
        """Upload a video to TikTok.

        Automatically uses chunked upload for files larger than 64 MB.

        Args:
            video_path: Path to the video file.
            title: Video title.
            description: Video description.
            privacy_status: One of: public, mutual_follow_friends, followers, private.
            allow_comments: Whether to allow comments.
            allow_duet: Whether to allow duets.
            allow_stitch: Whether to allow stitches.

        Returns:
            The publish_id for tracking the upload status, or None on failure.
        """
        path = Path(video_path)
        if not path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            logger.error(f"Video file too large: {file_size} bytes (max: {MAX_FILE_SIZE})")
            return None

        logger.info(f"Starting upload for {video_path} ({file_size} bytes)")

        # Determine chunk size
        if file_size <= MAX_CHUNK_SIZE:
            chunk_size = file_size
            total_chunks = 1
        else:
            total_chunks = (file_size + MAX_CHUNK_SIZE - 1) // MAX_CHUNK_SIZE
            chunk_size = (file_size + total_chunks - 1) // total_chunks
            chunk_size = min(MAX_CHUNK_SIZE, max(MIN_CHUNK_SIZE, chunk_size))
            total_chunks = (file_size + chunk_size - 1) // chunk_size

        init_data = self._init_video_upload(
            title=title,
            description=description,
            privacy_status=privacy_status,
            file_size=file_size,
            chunk_size=chunk_size,
            total_chunk_count=total_chunks,
            allow_comments=allow_comments,
            allow_duet=allow_duet,
            allow_stitch=allow_stitch,
        )

        if not init_data:
            return None

        publish_id = init_data.get("publish_id")
        upload_url = init_data.get("upload_url")

        if not publish_id or not upload_url:
            logger.error("Missing publish_id or upload_url in init response")
            return None

        logger.info(f"Upload initialized: publish_id={publish_id}")

        # Upload chunks
        with open(path, "rb") as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                if not self._upload_chunk(upload_url, chunk, i, total_chunks):
                    logger.error(f"Upload failed at chunk {i + 1}")
                    return None

        logger.info(f"Upload complete: publish_id={publish_id}")
        return publish_id

    @_retry_on_rate_limit
    def check_upload_status(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Check if video is published/review/failed.

        Args:
            video_id: The publish_id returned by upload_video.

        Returns:
            Dict with status info, or None if failed.
        """
        logger.info(f"Checking status for publish_id={video_id}")
        try:
            response = requests.post(
                VIDEO_STATUS_ENDPOINT,
                headers=self._get_auth_headers(),
                json={"publish_id": video_id},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Status check failed: {e}")
            return None

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Status API error {error_code}: {error_msg}")
            return None

        status_data = data.get("data", {})
        status = status_data.get("status")
        logger.info(f"Status: {status}")

        if status in ("PUBLISH_FAILED", "FAILED"):
            fail_reason = status_data.get("fail_reason", "Unknown")
            logger.error(f"Upload failed: {fail_reason}")
            return status_data

        return status_data

    @_retry_on_rate_limit
    def get_video_analytics(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get views, likes, comments, shares for a video.

        Args:
            video_id: The TikTok video ID.

        Returns:
            Dict with analytics data, or None if failed.
        """
        logger.info(f"Fetching analytics for video_id={video_id}")
        try:
            response = requests.post(
                VIDEO_QUERY_ENDPOINT,
                headers=self._get_auth_headers(),
                json={"filters": {"video_ids": [video_id]}},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Analytics request failed: {e}")
            return None

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Analytics API error {error_code}: {error_msg}")
            return None

        videos = data.get("data", {}).get("videos", [])
        if not videos:
            logger.warning(f"No analytics found for video_id={video_id}")
            return {}

        video = videos[0]
        result = {
            "video_id": video_id,
            "view_count": video.get("view_count", 0),
            "like_count": video.get("like_count", 0),
            "comment_count": video.get("comment_count", 0),
            "share_count": video.get("share_count", 0),
        }

        logger.info(
            f"Video {video_id} analytics: "
            f"{result['view_count']} views, "
            f"{result['like_count']} likes, "
            f"{result['comment_count']} comments, "
            f"{result['share_count']} shares"
        )
        return result

    @_retry_on_rate_limit
    def get_creator_info(self) -> Optional[Dict[str, Any]]:
        """Get creator username, follower count, etc.

        Returns:
            Dict with creator info, or None if failed.
        """
        logger.info("Fetching creator info")
        try:
            response = requests.get(
                USER_INFO_ENDPOINT,
                headers=self._get_auth_headers(),
                params={"fields": ["open_id", "union_id", "avatar_url", "display_name", "follower_count", "following_count", "likes_count"]},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Creator info request failed: {e}")
            return None

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Creator info API error {error_code}: {error_msg}")
            return None

        user_data = data.get("data", {}).get("user", {})
        if not user_data:
            logger.warning("No user data found")
            return {}

        result = {
            "open_id": user_data.get("open_id"),
            "union_id": user_data.get("union_id"),
            "username": user_data.get("display_name"),
            "avatar_url": user_data.get("avatar_url"),
            "follower_count": user_data.get("follower_count", 0),
            "following_count": user_data.get("following_count", 0),
            "likes_count": user_data.get("likes_count", 0),
        }

        logger.info(
            f"Creator info: {result['username']} - "
            f"{result['follower_count']} followers"
        )
        return result

    def list_videos(self, max_count: int = 20) -> List[Dict[str, Any]]:
        """List uploaded videos.

        Args:
            max_count: Maximum number of videos to return.

        Returns:
            List of video dictionaries.
        """
        logger.info(f"Listing videos (max_count={max_count})")
        try:
            response = requests.get(
                VIDEO_LIST_ENDPOINT,
                headers=self._get_auth_headers(),
                params={"max_count": max_count},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"List videos failed: {e}")
            return []

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"List videos API error {error_code}: {error_msg}")
            return []

        videos = data.get("data", {}).get("videos", [])
        logger.info(f"Retrieved {len(videos)} videos")
        return videos
