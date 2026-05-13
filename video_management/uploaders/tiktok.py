"""
TikTok Content Posting API uploader.

Provides chunked video upload, status polling, and analytics retrieval
via the TikTok for Developers API (v2).
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
VIDEO_INIT_ENDPOINT = f"{TIKTOK_API_BASE}/post/publish/video/init/"
VIDEO_STATUS_ENDPOINT = f"{TIKTOK_API_BASE}/post/publish/status/"
VIDEO_LIST_ENDPOINT = f"{TIKTOK_API_BASE}/video/list/"
VIDEO_QUERY_ENDPOINT = f"{TIKTOK_API_BASE}/video/query/"

# TikTok API constraints
MAX_CHUNK_SIZE = 64 * 1024 * 1024  # 64 MB
MIN_CHUNK_SIZE = 5 * 1024 * 1024   # 5 MB

PRIVACY_LEVELS = {
    "public": "PUBLIC_TO_EVERYONE",
    "mutual_follow_friends": "MUTUAL_FOLLOW_FRIENDS",
    "followers": "FOLLOWER_OF_CREATOR",
    "private": "SELF_ONLY",
}


class TikTokAPIError(Exception):
    """Raised when the TikTok API returns an error response."""

    def __init__(self, message: str, code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.response_data = response_data or {}


class TikTokUploader:
    """Upload videos to TikTok using the Content Posting API."""

    def __init__(self, client_key: str, client_secret: str) -> None:
        """Initialize with TikTok app credentials.

        Args:
            client_key: TikTok app client key.
            client_secret: TikTok app client secret.
        """
        self.client_key = client_key
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Return a reusable httpx Client instance."""
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def _close_client(self) -> None:
        """Close the underlying httpx Client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _get_auth_headers(self) -> Dict[str, str]:
        """Return headers with the current access token."""
        if not self._access_token:
            self.get_access_token()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def get_access_token(self) -> str:
        """Obtain an OAuth2 client_credentials access token.

        Returns:
            The access token string.

        Raises:
            TikTokAPIError: If the token request fails.
        """
        if self._access_token and time.time() < self._token_expires_at - 60:
            logger.debug("Reusing cached access token")
            return self._access_token

        logger.info("Requesting TikTok access token")
        try:
            response = self._get_client().post(
                TOKEN_ENDPOINT,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Token request failed: {exc.response.status_code} {exc.response.text}")
            raise TikTokAPIError(
                f"Token request failed: {exc.response.status_code}",
                code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(f"Token request error: {exc}")
            raise TikTokAPIError(f"Token request error: {exc}") from exc

        error_code = data.get("error_code")
        if error_code:
            error_msg = data.get("description", "Unknown error")
            logger.error(f"Token API error {error_code}: {error_msg}")
            raise TikTokAPIError(
                f"Token API error {error_code}: {error_msg}",
                code=error_code,
                response_data=data,
            )

        self._access_token = data.get("access_token")
        expires_in = data.get("expires_in", 7200)
        self._token_expires_at = time.time() + expires_in

        if not self._access_token:
            raise TikTokAPIError("No access_token in response", response_data=data)

        logger.info(f"Access token obtained (expires in {expires_in}s)")
        return self._access_token

    def _init_video_upload(
        self,
        title: str,
        description: str,
        privacy_level: str,
        file_size: int,
        chunk_size: int,
        total_chunk_count: int,
    ) -> Dict[str, Any]:
        """Initialize a video upload session.

        Args:
            title: Video title.
            description: Video description.
            privacy_level: One of the supported privacy levels.
            file_size: Total file size in bytes.
            chunk_size: Size of each chunk in bytes.
            total_chunk_count: Total number of chunks.

        Returns:
            The API response containing publish_id and upload_url.

        Raises:
            TikTokAPIError: If the API returns an error.
            ValueError: If the privacy level is invalid.
        """
        if privacy_level not in PRIVACY_LEVELS:
            raise ValueError(
                f"Invalid privacy_level '{privacy_level}'. "
                f"Must be one of: {', '.join(PRIVACY_LEVELS.keys())}"
            )

        body = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
            "title": title,
            "description": description,
            "privacy_level": PRIVACY_LEVELS[privacy_level],
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        }

        logger.info(f"Initializing upload: {title} ({file_size} bytes, {total_chunk_count} chunks)")
        try:
            response = self._get_client().post(
                VIDEO_INIT_ENDPOINT,
                headers=self._get_auth_headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Upload init failed: {exc.response.status_code} {exc.response.text}")
            raise TikTokAPIError(
                f"Upload init failed: {exc.response.status_code}",
                code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(f"Upload init error: {exc}")
            raise TikTokAPIError(f"Upload init error: {exc}") from exc

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Upload init API error {error_code}: {error_msg}")
            raise TikTokAPIError(
                f"Upload init API error {error_code}: {error_msg}",
                code=error_code,
                response_data=data,
            )

        return data.get("data", {})

    def _upload_chunk(
        self,
        upload_url: str,
        chunk_data: bytes,
        chunk_index: int,
        total_chunks: int,
    ) -> None:
        """Upload a single chunk.

        Args:
            upload_url: The URL returned by the init endpoint.
            chunk_data: The chunk bytes.
            chunk_index: Zero-based chunk index.
            total_chunks: Total number of chunks.

        Raises:
            TikTokAPIError: If the chunk upload fails.
        """
        content_range = f"bytes {chunk_index * len(chunk_data)}-{chunk_index * len(chunk_data) + len(chunk_data) - 1}/{total_chunks * len(chunk_data)}"

        logger.info(f"Uploading chunk {chunk_index + 1}/{total_chunks} ({len(chunk_data)} bytes)")
        try:
            response = self._get_client().put(
                upload_url,
                content=chunk_data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": content_range,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                f"Chunk {chunk_index + 1} upload failed: {exc.response.status_code} {exc.response.text}"
            )
            raise TikTokAPIError(
                f"Chunk {chunk_index + 1} upload failed: {exc.response.status_code}",
                code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(f"Chunk {chunk_index + 1} upload error: {exc}")
            raise TikTokAPIError(f"Chunk {chunk_index + 1} upload error: {exc}") from exc

        logger.info(f"Chunk {chunk_index + 1}/{total_chunks} uploaded successfully")

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        privacy_level: str = "private",
    ) -> str:
        """Upload a video to TikTok.

        Automatically uses chunked upload for files larger than 64 MB.

        Args:
            video_path: Path to the video file.
            title: Video title.
            description: Video description.
            privacy_level: One of: public, mutual_follow_friends, followers, private.

        Returns:
            The publish_id for tracking the upload status.

        Raises:
            FileNotFoundError: If the video file does not exist.
            TikTokAPIError: If any API call fails.
            ValueError: If the privacy level is invalid.
        """
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size = path.stat().st_size
        logger.info(f"Starting upload for {video_path} ({file_size} bytes)")

        # Determine chunk size
        if file_size <= MAX_CHUNK_SIZE:
            chunk_size = file_size
            total_chunks = 1
        else:
            # Calculate chunk count so each chunk is within bounds
            total_chunks = (file_size + MAX_CHUNK_SIZE - 1) // MAX_CHUNK_SIZE
            chunk_size = (file_size + total_chunks - 1) // total_chunks
            # Ensure chunk size is within limits
            chunk_size = min(MAX_CHUNK_SIZE, max(MIN_CHUNK_SIZE, chunk_size))
            total_chunks = (file_size + chunk_size - 1) // chunk_size

        init_data = self._init_video_upload(
            title=title,
            description=description,
            privacy_level=privacy_level,
            file_size=file_size,
            chunk_size=chunk_size,
            total_chunk_count=total_chunks,
        )

        publish_id = init_data.get("publish_id")
        upload_url = init_data.get("upload_url")

        if not publish_id or not upload_url:
            raise TikTokAPIError(
                "Missing publish_id or upload_url in init response",
                response_data=init_data,
            )

        logger.info(f"Upload initialized: publish_id={publish_id}")

        # Upload chunks
        with open(path, "rb") as f:
            for i in range(total_chunks):
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                self._upload_chunk(upload_url, chunk, i, total_chunks)

        logger.info(f"Upload complete: publish_id={publish_id}")
        return publish_id

    def check_upload_status(self, publish_id: str, max_attempts: int = 30, interval: int = 10) -> Dict[str, Any]:
        """Poll for video processing status.

        Args:
            publish_id: The publish ID returned by upload_video.
            max_attempts: Maximum number of polling attempts.
            interval: Seconds between polling attempts.

        Returns:
            The final status response from the API.

        Raises:
            TikTokAPIError: If the status check fails.
        """
        logger.info(f"Polling status for publish_id={publish_id}")

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._get_client().post(
                    VIDEO_STATUS_ENDPOINT,
                    headers=self._get_auth_headers(),
                    json={"publish_id": publish_id},
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                logger.error(f"Status check failed: {exc.response.status_code} {exc.response.text}")
                raise TikTokAPIError(
                    f"Status check failed: {exc.response.status_code}",
                    code=exc.response.status_code,
                ) from exc
            except httpx.RequestError as exc:
                logger.error(f"Status check error: {exc}")
                raise TikTokAPIError(f"Status check error: {exc}") from exc

            error_code = data.get("error", {}).get("code")
            if error_code:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logger.error(f"Status API error {error_code}: {error_msg}")
                raise TikTokAPIError(
                    f"Status API error {error_code}: {error_msg}",
                    code=error_code,
                    response_data=data,
                )

            status_data = data.get("data", {})
            status = status_data.get("status")
            logger.info(f"Status check {attempt}/{max_attempts}: {status}")

            if status in ("PUBLISH_FAILED", "FAILED"):
                fail_reason = status_data.get("fail_reason", "Unknown")
                logger.error(f"Upload failed: {fail_reason}")
                raise TikTokAPIError(
                    f"Upload failed: {fail_reason}",
                    response_data=status_data,
                )

            if status == "PUBLISH_COMPLETE":
                logger.info(f"Upload complete: video_id={status_data.get('video_id')}")
                return status_data

            time.sleep(interval)

        logger.warning(f"Polling timed out after {max_attempts} attempts")
        return status_data

    def get_video_analytics(self, video_id: str) -> Dict[str, Any]:
        """Get basic analytics for a video.

        Args:
            video_id: The TikTok video ID.

        Returns:
            Dictionary containing video analytics.

        Raises:
            TikTokAPIError: If the API request fails.
        """
        logger.info(f"Fetching analytics for video_id={video_id}")
        try:
            response = self._get_client().post(
                VIDEO_QUERY_ENDPOINT,
                headers=self._get_auth_headers(),
                json={"filters": {"video_ids": [video_id]}},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Analytics request failed: {exc.response.status_code} {exc.response.text}")
            raise TikTokAPIError(
                f"Analytics request failed: {exc.response.status_code}",
                code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(f"Analytics request error: {exc}")
            raise TikTokAPIError(f"Analytics request error: {exc}") from exc

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"Analytics API error {error_code}: {error_msg}")
            raise TikTokAPIError(
                f"Analytics API error {error_code}: {error_msg}",
                code=error_code,
                response_data=data,
            )

        videos = data.get("data", {}).get("videos", [])
        if not videos:
            logger.warning(f"No analytics found for video_id={video_id}")
            return {}

        return videos[0]

    def list_videos(self, max_count: int = 20) -> List[Dict[str, Any]]:
        """List uploaded videos.

        Args:
            max_count: Maximum number of videos to return.

        Returns:
            List of video dictionaries.

        Raises:
            TikTokAPIError: If the API request fails.
        """
        logger.info(f"Listing videos (max_count={max_count})")
        try:
            response = self._get_client().get(
                VIDEO_LIST_ENDPOINT,
                headers=self._get_auth_headers(),
                params={"max_count": max_count},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"List videos failed: {exc.response.status_code} {exc.response.text}")
            raise TikTokAPIError(
                f"List videos failed: {exc.response.status_code}",
                code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error(f"List videos error: {exc}")
            raise TikTokAPIError(f"List videos error: {exc}") from exc

        error_code = data.get("error", {}).get("code")
        if error_code:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            logger.error(f"List videos API error {error_code}: {error_msg}")
            raise TikTokAPIError(
                f"List videos API error {error_code}: {error_msg}",
                code=error_code,
                response_data=data,
            )

        videos = data.get("data", {}).get("videos", [])
        logger.info(f"Retrieved {len(videos)} videos")
        return videos

    def __enter__(self) -> "TikTokUploader":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._close_client()
