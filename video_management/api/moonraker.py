"""Moonraker API client using httpx."""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
MAX_RETRIES = 3


class MoonrakerClient:
    """Async HTTP client for Moonraker (Klipper) API."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers=headers,
        )

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Make an HTTP request with retries."""
        url = f"{self.base_url}{path}"
        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {"result": data}
            except httpx.HTTPStatusError as exc:
                logger.error(
                    f"HTTP error {exc.response.status_code} on {method} {url}: {exc}"
                )
                return None
            except httpx.RequestError as exc:
                last_exception = exc
                logger.warning(
                    f"Request error on attempt {attempt}/{MAX_RETRIES} for {method} {url}: {exc}"
                )
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    f"Unexpected error on attempt {attempt}/{MAX_RETRIES} for {method} {url}: {exc}"
                )

        if last_exception:
            logger.error(f"All {MAX_RETRIES} attempts failed for {method} {url}: {last_exception}")
        return None

    async def connect(self) -> bool:
        """Test connection to Moonraker by fetching server info."""
        logger.info(f"Testing connection to Moonraker at {self.base_url}")
        data = await self._request("GET", "/server/info")
        if data is not None:
            logger.info("Successfully connected to Moonraker")
            return True
        logger.error("Failed to connect to Moonraker")
        return False

    async def get_timelapse_files(self) -> List[Dict[str, Any]]:
        """Get list of timelapse files from Moonraker.
        
        Returns all timelapse files in a single request.
        Moonraker's /server/files/list endpoint returns all files at once.
        """
        logger.debug("Fetching timelapse file list")
        data = await self._request("GET", "/server/files/list?root=timelapse")
        if data is None:
            return []
        result = data.get("result", [])
        if not isinstance(result, list):
            logger.warning(f"Unexpected timelapse list response format: {type(result)}")
            return []
        logger.info(f"Retrieved {len(result)} timelapse files")
        return result

    async def download_timelapse(self, filename: str, output_path: str) -> bool:
        """Download a timelapse file from Moonraker."""
        url = f"{self.base_url}/server/files/timelapse/{filename}"
        logger.info(f"Downloading timelapse: {filename} -> {output_path}")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.client.stream("GET", url, timeout=300.0) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0 and downloaded % (1024 * 1024) == 0:
                                    progress = (downloaded / total_size) * 100
                                    logger.info(f"Download progress: {progress:.1f}%")

                logger.info(f"Timelapse downloaded successfully: {output_path}")
                return True

            except httpx.HTTPStatusError as exc:
                logger.error(f"HTTP error {exc.response.status_code} downloading {filename}: {exc}")
                return False
            except httpx.RequestError as exc:
                logger.warning(
                    f"Download attempt {attempt}/{MAX_RETRIES} failed for {filename}: {exc}"
                )
            except Exception as exc:
                logger.warning(
                    f"Unexpected error on download attempt {attempt}/{MAX_RETRIES} for {filename}: {exc}"
                )

        logger.error(f"Failed to download {filename} after {MAX_RETRIES} attempts")
        return False

    async def get_printer_info(self) -> Optional[Dict[str, Any]]:
        """Get printer information from Moonraker."""
        logger.debug("Fetching printer info")
        data = await self._request("GET", "/printer/info")
        if data is None:
            return None
        result = data.get("result", data)
        logger.info("Retrieved printer info")
        return result if isinstance(result, dict) else None

    async def get_job_status(self) -> Optional[Dict[str, Any]]:
        """Get current print job status from Moonraker."""
        logger.debug("Fetching job status")
        data = await self._request(
            "GET",
            "/printer/objects/query",
            params={"print_stats": None},
        )
        if data is None:
            return None
        result = data.get("result", data)
        status = result.get("status", result) if isinstance(result, dict) else result
        logger.info("Retrieved job status")
        return status if isinstance(status, dict) else None

    async def get_server_files(self) -> List[Dict[str, Any]]:
        """Get all files from Moonraker server."""
        logger.debug("Fetching server files list")
        data = await self._request("GET", "/server/files/list")
        if data is None:
            return []
        result = data.get("result", [])
        if not isinstance(result, list):
            logger.warning(f"Unexpected server files response format: {type(result)}")
            return []
        logger.info(f"Retrieved {len(result)} server files")
        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
        logger.debug("Moonraker client closed")

    async def __aenter__(self) -> "MoonrakerClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
