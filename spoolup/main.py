#!/usr/bin/env python3
"""
SpoolUp Runtime Module
Main application for streaming 3D prints to YouTube
"""

# SSL/TLS compatibility settings for corporate networks
# Uncomment these lines if you encounter SSL errors:
# os.environ['PYTHONHTTPSVERIFY'] = '0'
# os.environ['SSL_CERT_FILE'] = ''
# os.environ['SSL_CERT_DIR'] = ''

import os
import sys
import json
import time
import ssl
import logging
import argparse
import subprocess
import threading
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Callable

import requests
import urllib3
import websocket
import google.auth
import httplib2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Optional import for SSL disable functionality
_AuthHttpImportError = None
try:
    import google_auth_httplib2

    HAS_AUTH_HTTP = True
except ImportError as e:
    HAS_AUTH_HTTP = False
    _AuthHttpImportError = str(e)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
]

_log_file = os.path.join(tempfile.gettempdir(), "spoolup.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_file),
    ],
)
logger = logging.getLogger(__name__)


class Config:
    DEFAULTS = {
        "moonraker_url": "http://localhost:7125",
        "webcam_url": "http://localhost:8080/?action=stream",
        "timelapse_dir": os.path.join(tempfile.gettempdir(), "spoolup", "timelapse"),
        "client_secrets_file": "client_secrets.json",
        "token_file": "youtube_token.json",
        "stream_resolution": "1280x720",
        "stream_fps": 15,
        "stream_bitrate": "750k",
        "timelapse_mode": "local",  # "local" or "remote"
        "printer_ip": "",  # For remote timelapse mode (e.g., "192.168.1.100")
        "youtube_category_id": "28",
        "video_privacy": "private",
        "stream_privacy": "unlisted",
        "enable_live_stream": True,
        "enable_timelapse_upload": True,
        "retry_attempts": 3,
        "retry_delay": 5,
        "disable_ssl_verify": False,
    }

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.values = self.DEFAULTS.copy()
        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.values.update(json.load(f))
                logger.info(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

    def save(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.values, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value: Any):
        self.values[key] = value


class MoonrakerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.ws = None
        self.ws_url = (
            base_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/websocket"
        )
        self.message_id = 0
        self.callbacks: Dict[str, Callable] = {}
        self.connected = False
        self.print_state = "unknown"
        self.current_file = None
        self._initial_state_handled = False
        self._subscription_msg_id: Optional[int] = None
        self._subscription_pending = False
        self._ws_thread: Optional[threading.Thread] = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0
        self._shutdown = False
        self._last_ping_time = 0.0
        self._ping_interval = 30.0

    def connect_websocket(self):
        try:
            if self._shutdown:
                logger.debug("WebSocket shutdown requested, not connecting")
                return False

            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_ping=self._on_ping,
                on_pong=self._on_pong,
            )
            logger.info(f"Connecting to Moonraker WebSocket at {self.ws_url}")

            self._ws_thread = threading.Thread(target=self._run_websocket_forever)
            self._ws_thread.daemon = True
            self._ws_thread.start()

            timeout = 10
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)

            if self.connected:
                self._reconnect_delay = 1.0
                logger.info("WebSocket connected successfully")

            return self.connected

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False

    def _run_websocket_forever(self):
        if not self.ws:
            return
        try:
            self.ws.run_forever(
                ping_interval=self._ping_interval,
                ping_payload="keepalive",
            )
        except Exception as e:
            logger.error(f"WebSocket run_forever error: {e}")
        finally:
            if not self._shutdown:
                logger.warning("WebSocket connection ended, will attempt reconnect")

    def _on_ping(self, ws, message):
        logger.debug(f"WebSocket ping received: {message}")

    def _on_pong(self, ws, message):
        self._last_ping_time = time.time()
        logger.debug(f"WebSocket pong received: {message}")

    def _on_open(self, ws):
        logger.info("Moonraker WebSocket connected")
        self.connected = True
        self._subscription_pending = True
        self._subscription_msg_id = self._send_jsonrpc(
            "printer.objects.subscribe",
            {"objects": {"print_stats": None, "virtual_sdcard": None}},
        )

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)

            if "method" in data:
                method = data["method"]
                params = data.get("params", [])

                if method == "notify_status_update":
                    self._handle_status_update(params[0] if params else {})

            elif "id" in data and data["id"] == self._subscription_msg_id:
                if data.get("error"):
                    logger.error(f"Subscription failed: {data['error']}")
                else:
                    logger.info("Subscription confirmed")
                    self._subscription_pending = False
                    # Extract initial state from subscription response
                    result = data.get("result", {})
                    if "status" in result:
                        initial_status = result["status"]
                        logger.info(
                            f"Received initial state from subscription: {initial_status}"
                        )
                        self._handle_status_update(initial_status)

            elif "id" in data and data["id"] in self.callbacks:
                callback = self.callbacks.pop(data["id"])
                callback(data.get("result"), data.get("error"))

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        was_connected = self.connected
        self.connected = False
        self._subscription_pending = False
        self._subscription_msg_id = None

        if was_connected:
            logger.warning(
                f"Moonraker WebSocket disconnected (code: {close_status_code}, msg: {close_msg})"
            )
        else:
            logger.debug(f"WebSocket connection closed (code: {close_status_code})")

    def _send_jsonrpc(self, method: str, params: Optional[dict] = None) -> int:
        self.message_id += 1
        msg_id = self.message_id

        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": msg_id}
        if params is not None:
            message["params"] = params

        if self.ws and self.connected:
            self.ws.send(json.dumps(message))

        return msg_id

    def _handle_status_update(self, status: dict):
        if "print_stats" in status:
            stats = status["print_stats"]

            if "state" in stats:
                new_state = stats["state"]
                if new_state != self.print_state:
                    old_state = self.print_state
                    self.print_state = new_state
                    logger.info(f"Print state changed: {old_state} -> {new_state}")

                    if new_state == "printing" and old_state not in ["printing"]:
                        if self._initial_state_handled:
                            logger.debug(
                                f"Print start ignored - initial state already handled"
                            )
                            return
                        logger.info(
                            f"Triggering print start callback for: {stats.get('filename')}"
                        )
                        self._initial_state_handled = True
                        self.on_print_started(stats.get("filename"))
                    elif new_state == "complete" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
                        self._initial_state_handled = False
                        self.on_print_completed(stats.get("filename"))
                    elif new_state == "cancelled" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
                        self._initial_state_handled = False
                        self.on_print_cancelled(stats.get("filename"))
                    elif new_state == "error" and old_state == "printing":
                        logger.warning(
                            "Print error detected - stream continuing. Waiting for recovery or completion..."
                        )

            if "filename" in stats:
                self.current_file = stats["filename"]

    def on_print_started(self, filename: str):
        logger.info(f"Print started: {filename}")

    def on_print_completed(self, filename: str):
        logger.info(f"Print completed: {filename}")

    def on_print_cancelled(self, filename: str):
        logger.info(f"Print cancelled: {filename}")

    def get_printer_info(self) -> dict:
        try:
            response = requests.get(f"{self.base_url}/printer/info")
            response.raise_for_status()
            return response.json().get("result", {})
        except Exception as e:
            logger.error(f"Failed to get printer info: {e}")
            return {}

    def get_timelapse_config(self) -> dict:
        try:
            response = requests.get(f"{self.base_url}/server/timelapse/settings")
            response.raise_for_status()
            return response.json().get("result", {})
        except Exception as e:
            logger.error(f"Failed to get timelapse config: {e}")
            return {}

    def get_print_status(self) -> dict:
        try:
            response = requests.get(
                f"{self.base_url}/printer/objects/query", params={"print_stats": None}
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            return result.get("status", {}).get("print_stats", {})
        except Exception as e:
            logger.error(f"Failed to get print status: {e}")
            return {}

    def start_reconnection_loop(self):
        def reconnect_loop():
            logger.info("WebSocket reconnection loop started")
            while not self._shutdown:
                if not self.connected:
                    logger.info(
                        f"Attempting WebSocket reconnect (delay: {self._reconnect_delay:.1f}s)"
                    )
                    if self.connect_websocket():
                        logger.info("WebSocket reconnected successfully")
                        self._reconnect_delay = 1.0
                    else:
                        self._reconnect_delay = min(
                            self._reconnect_delay * 1.5, self._max_reconnect_delay
                        )
                        logger.warning(
                            f"Reconnect failed, next attempt in {self._reconnect_delay:.1f}s"
                        )
                time.sleep(1)
            logger.info("WebSocket reconnection loop stopped")

        reconnect_thread = threading.Thread(target=reconnect_loop)
        reconnect_thread.daemon = True
        reconnect_thread.start()
        return reconnect_thread

    def disconnect(self):
        self._shutdown = True
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket: {e}")
        self.connected = False

    def get_print_stats(self) -> Dict[str, Any]:
        """Fetch comprehensive print statistics for broadcast description."""
        stats = {}
        try:
            response = requests.get(
                f"{self.base_url}/printer/objects/query?print_stats&virtual_sdcard&toolhea",
                params={
                    "print_stats": None,
                    "virtual_sdcard": None,
                    "toolhead": None,
                },
                timeout=10,
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            status = result.get("status", {})

            print_stats = status.get("print_stats", {})
            virtual_sdcard = status.get("virtual_sdcard", {})
            toolhead = status.get("toolhead", {})

            speed = toolhead.get("speed", 0)
            stats["speed"] = f"{speed:.0f} mm/s" if speed else "100 mm/s"

            filament_mm = print_stats.get("filament_used", 0)
            stats["filament_used"] = (
                f"{filament_mm / 1000:.2f} m" if filament_mm else "0.00 m"
            )

            current_layer = virtual_sdcard.get("layer", 0)
            total_layers = virtual_sdcard.get("layer_count", 0)
            stats["current_layer"] = current_layer if current_layer else 0
            stats["total_layers"] = total_layers if total_layers else 0

            print_duration = print_stats.get("print_duration", 0)
            total_duration = print_stats.get("total_duration", 0)

            if total_duration:
                total_td = timedelta(seconds=int(total_duration))
                hours, remainder = divmod(total_td.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                stats["total_time"] = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                stats["total_time"] = "0:00:00"

            progress = virtual_sdcard.get("progress", 0)
            if progress > 0 and print_duration > 0:
                estimated_total = print_duration / progress
                remaining = estimated_total - print_duration
                remaining_td = timedelta(seconds=int(remaining))
                hours, remainder = divmod(remaining_td.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                stats["estimate"] = f"{hours}:{minutes:02d}:{seconds:02d}"

                eta_time = datetime.now() + remaining_td
                stats["eta"] = eta_time.strftime("%I:%M %p")
            else:
                stats["estimate"] = "Calculating..."
                stats["eta"] = "Calculating..."

            if progress > 0 and print_duration > 0:
                estimated_total = print_duration / progress
                total_td = timedelta(seconds=int(estimated_total))
                hours, remainder = divmod(total_td.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                stats["slicer_time"] = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                stats["slicer_time"] = "N/A"

            stats["flow"] = "N/A"

        except Exception as e:
            logger.error(f"Failed to get print stats: {e}")

        return stats


class YouTubeStreamer:
    def __init__(self, config: Config, youtube_service):
        self.config = config
        self.youtube = youtube_service
        self.ffmpeg_process = None
        self.live_broadcast = None
        self.live_stream = None
        self.stream_url = None
        self.is_streaming = False
        self.display_title: Optional[str] = None
        self._health_check_thread = None
        self._description_update_thread = None

    def _check_ffmpeg_available(self) -> bool:
        """Check if FFmpeg is installed and available in PATH."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _map_resolution_to_youtube_format(self, resolution: str) -> str:
        resolution_map = {
            "426x240": "240p",
            "640x360": "360p",
            "854x480": "480p",
            "1280x720": "720p",
            "1920x1080": "1080p",
            "2560x1440": "1440p",
            "3840x2160": "2160p",
        }
        return resolution_map.get(resolution, "variable")

    def _map_fps_to_youtube_format(self, fps: int) -> str:
        return "60fps" if fps >= 45 else "30fps"

    def create_live_stream(
        self, title: str, print_stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            if not title:
                title = "3D Print"

            # Clean up filename: remove .gcode extension and replace + with spaces
            display_title = title.replace(".gcode", "").replace("+", " ")
            self.display_title = display_title
            logger.info(f"Creating stream with display_title: {display_title}")

            config_resolution: str = self.config.get("stream_resolution") or "1280x720"
            config_fps: int = self.config.get("stream_fps") or 30

            youtube_resolution = self._map_resolution_to_youtube_format(
                config_resolution
            )
            youtube_fps = self._map_fps_to_youtube_format(config_fps)

            stream_insert_data = {
                "snippet": {
                    "title": f"Live Stream - {display_title}",
                },
                "cdn": {
                    "ingestionType": "rtmp",
                    "resolution": youtube_resolution,
                    "frameRate": youtube_fps,
                },
                "contentDetails": {"isReusable": False},
            }

            logger.info("Creating YouTube live stream...")
            stream = (
                self.youtube.liveStreams()
                .insert(part="snippet,cdn,contentDetails", body=stream_insert_data)
                .execute()
            )

            self.live_stream = stream
            stream_id = stream["id"]
            ingestion_info = stream["cdn"]["ingestionInfo"]
            self.stream_url = (
                f"{ingestion_info['ingestionAddress']}/{ingestion_info['streamName']}"
            )

            logger.info(f"Live stream created: {stream_id}")
            logger.info(f"Stream URL: {self.stream_url}")

            start_time = datetime.now(timezone.utc)
            end_time = start_time + timedelta(hours=24)

            # Build description with print statistics
            description = self._build_broadcast_description(display_title, print_stats)

            broadcast_title = f"3D Printing: {display_title}"
            logger.info(f"Broadcast title will be: {broadcast_title}")

            broadcast_insert_data = {
                "snippet": {
                    "title": broadcast_title,
                    "description": description,
                    "scheduledStartTime": start_time.isoformat(),
                    "scheduledEndTime": end_time.isoformat(),
                },
                "status": {
                    "privacyStatus": self.config.get("stream_privacy", "unlisted"),
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "monitorStream": {
                        "enableMonitorStream": True,
                        "broadcastStreamDelayMs": 0,
                    },
                    "enableAutoStart": False,
                    "enableAutoStop": False,
                },
            }

            logger.info("Creating live broadcast...")
            broadcast = (
                self.youtube.liveBroadcasts()
                .insert(
                    part="snippet,status,contentDetails", body=broadcast_insert_data
                )
                .execute()
            )

            self.live_broadcast = broadcast
            broadcast_id = broadcast["id"]

            logger.info(f"Live broadcast created: {broadcast_id}")

            self.youtube.liveBroadcasts().bind(
                part="id,contentDetails", id=broadcast_id, streamId=stream_id
            ).execute()

            logger.info("Stream bound to broadcast")
            return True
        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create live stream: {e}")
            return False

    def _build_broadcast_description(
        self, display_title: str, print_stats: Optional[Dict[str, Any]]
    ) -> str:
        """Build broadcast description with print statistics."""
        lines = [
            f"Live stream of 3D print: {display_title}",
            "",
            "📊 Print Statistics",
            "━" * 40,
        ]

        if print_stats:
            # Extract statistics
            speed = print_stats.get("speed", "N/A")
            flow = print_stats.get("flow", "N/A")
            filament = print_stats.get("filament_used", "N/A")
            current_layer = print_stats.get("current_layer", "N/A")
            total_layers = print_stats.get("total_layers", "N/A")
            estimate = print_stats.get("estimate", "N/A")
            slicer_time = print_stats.get("slicer_time", "N/A")
            total_time = print_stats.get("total_time", "N/A")
            eta = print_stats.get("eta", "N/A")

            # Format statistics in a table-like layout
            lines.extend(
                [
                    f"Speed:        {speed}",
                    f"Flow:         {flow}",
                    f"Filament:     {filament}",
                    f"Layer:        {current_layer} of {total_layers}",
                    "",
                    f"Estimate:     {estimate}",
                    f"Slicer:       {slicer_time}",
                    f"Total:        {total_time}",
                    f"ETA:          {eta}",
                ]
            )
        else:
            lines.append("Statistics will be updated as the print progresses...")

        lines.extend(
            [
                "",
                "━" * 40,
                "🔴 Live from Klipper 3D Printer",
                f"⏱️  Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            ]
        )

        return "\n".join(lines)

    def _wait_for_stream_active(self, stream_id: str, timeout: int = 30) -> bool:
        """Wait for the stream to become active (receiving data from FFmpeg)."""
        logger.info(f"Waiting for stream {stream_id} to become active...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                stream = (
                    self.youtube.liveStreams()
                    .list(part="status", id=stream_id)
                    .execute()
                )
                if stream.get("items"):
                    status = stream["items"][0]["status"]["streamStatus"]
                    logger.info(f"Stream status: {status}")
                    if status == "active":
                        logger.info("Stream is now active")
                        return True
                    elif status == "error":
                        logger.error("Stream is in error state")
                        return False
            except Exception as e:
                logger.warning(f"Failed to check stream status: {e}")
            time.sleep(2)
        logger.warning(f"Stream did not become active within {timeout} seconds")
        return False

    def _transition_broadcast(self, broadcast_id: str, status: str) -> bool:
        try:
            broadcast = (
                self.youtube.liveBroadcasts()
                .list(part="status", id=broadcast_id)
                .execute()
            )

            if not broadcast.get("items"):
                logger.warning(f"Broadcast {broadcast_id} not found")
                return False

            current_status = broadcast["items"][0]["status"]["lifeCycleStatus"]

            valid_transitions = {
                "created": ["ready"],
                "ready": ["testing", "live"],
                "testStarting": ["testing"],
                "testing": ["live"],
                "liveStarting": ["live"],
                "live": ["complete"],
            }

            if current_status == status:
                logger.info(f"Broadcast already in '{status}' state")
                return True

            # Handle intermediate transition states
            if current_status == "testStarting" and status == "testing":
                logger.info("Broadcast is transitioning to testing, waiting...")
                time.sleep(3)
                return self._transition_broadcast(broadcast_id, status)

            if current_status == "liveStarting" and status == "live":
                logger.info("Broadcast is transitioning to live, waiting...")
                time.sleep(3)
                return self._transition_broadcast(broadcast_id, status)

            if status not in valid_transitions.get(current_status, []):
                logger.warning(
                    f"Cannot transition from '{current_status}' to '{status}'"
                )
                return False

            self.youtube.liveBroadcasts().transition(
                id=broadcast_id, part="status", broadcastStatus=status
            ).execute()
            logger.info(f"Broadcast transitioned from '{current_status}' to '{status}'")
            return True
        except Exception as e:
            logger.error(f"Failed to transition broadcast: {e}")
            return False

    def _check_stream_health(self) -> tuple[bool, str]:
        """Check stream health status.

        Returns:
            Tuple of (is_healthy, status_message)
        """
        try:
            if not self.live_stream:
                return False, "No live stream"
            logger.info(f"Checking stream health for {self.live_stream['id']}...")
            stream = (
                self.youtube.liveStreams()
                .list(part="status", id=self.live_stream["id"])
                .execute()
            )
            if not stream.get("items"):
                logger.warning("Stream not found in health check")
                return False, "Stream not found"
            status = stream["items"][0]["status"]
            stream_status = status.get("streamStatus")
            health = status.get("healthStatus", {}).get("status")

            logger.info(f"Stream status: {stream_status}, Health: {health}")

            if stream_status == "error":
                logger.error("Stream is in error state")
                return False, f"Stream error state"
            if stream_status == "inactive":
                logger.warning("Stream is inactive")
                return False, "Stream inactive"
            return True, f"Status: {stream_status}, Health: {health}"
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            return False, f"Health check error: {e}"

    def _health_check_loop(self):
        consecutive_failures = 0
        stream_start_time = time.time()
        startup_grace_period = 600
        check_count = 0

        logger.info("Health check loop started")
        while self.is_streaming:
            time.sleep(30)
            if not self.is_streaming:
                logger.info("Health check loop exiting - is_streaming is False")
                break

            check_count += 1
            elapsed = time.time() - stream_start_time
            logger.info(f"Health check #{check_count} after {elapsed:.0f}s")

            is_healthy, message = self._check_stream_health()

            if is_healthy:
                if consecutive_failures > 0:
                    logger.info(
                        f"Health check recovered after {consecutive_failures} failures"
                    )
                consecutive_failures = 0
                logger.info(f"Health check passed: {message}")
            else:
                consecutive_failures += 1
                logger.warning(
                    f"Health check failed ({consecutive_failures} failures): {message}"
                )

                max_failures_during_grace = 12
                max_failures_after_grace = 6

                if elapsed < startup_grace_period:
                    max_allowed = max_failures_during_grace
                    period = "grace period"
                else:
                    max_allowed = max_failures_after_grace
                    period = "after grace period"

                if consecutive_failures < max_allowed:
                    logger.info(
                        f"Within {period} ({consecutive_failures}/{max_allowed} failures), continuing..."
                    )
                    continue
                else:
                    logger.error(
                        f"TOO MANY FAILURES {period}: {consecutive_failures} >= {max_allowed}"
                    )

                logger.error("STOPPING STREAM DUE TO HEALTH CHECK FAILURES")
                self.stop_streaming()
                break

        logger.info("Health check loop ended")

    def _start_health_monitor(self):
        self._health_check_thread = threading.Thread(target=self._health_check_loop)
        self._health_check_thread.daemon = True
        self._health_check_thread.start()

    def _update_broadcast_description(self, description: str) -> bool:
        """Update the live broadcast description while preserving other snippet fields."""
        try:
            if not self.live_broadcast:
                return False
            broadcast_id = self.live_broadcast["id"]

            # Fetch current broadcast details to get required fields
            broadcast = (
                self.youtube.liveBroadcasts()
                .list(part="snippet", id=broadcast_id)
                .execute()
            )

            if not broadcast.get("items"):
                logger.warning(f"Broadcast {broadcast_id} not found for update")
                return False

            snippet = broadcast["items"][0]["snippet"]

            self.youtube.liveBroadcasts().update(
                part="snippet",
                body={
                    "id": broadcast_id,
                    "snippet": {
                        "title": snippet.get("title", ""),
                        "description": description,
                        "scheduledStartTime": snippet.get("scheduledStartTime"),
                        "scheduledEndTime": snippet.get("scheduledEndTime"),
                    },
                },
            ).execute()
            logger.info(f"Successfully updated broadcast {broadcast_id} description")
            return True
        except Exception as e:
            logger.error(f"Failed to update broadcast description: {e}")
            return False

    def _description_update_loop(self, get_print_stats_callback):
        """Periodically update broadcast description with fresh statistics."""
        update_interval = 15
        last_update = 0
        logger.info("Description update loop started")
        while self.is_streaming:
            time.sleep(1)
            if not self.is_streaming:
                logger.info("Description update loop stopping - stream ended")
                break
            elapsed = time.time() - last_update
            if elapsed < update_interval:
                continue
            try:
                logger.info("Fetching fresh print stats for description update...")
                print_stats = get_print_stats_callback()
                logger.info(f"Got print stats: {print_stats}")
                if print_stats and self.display_title:
                    description = self._build_broadcast_description(
                        self.display_title, print_stats
                    )
                    logger.info(f"Built description, attempting update...")
                    if self._update_broadcast_description(description):
                        last_update = time.time()
                        logger.info(
                            "Broadcast description updated successfully with fresh stats"
                        )
                    else:
                        logger.warning("Failed to update broadcast description")
                else:
                    logger.warning(
                        f"Missing data - print_stats: {bool(print_stats)}, display_title: {self.display_title}"
                    )
            except Exception as e:
                logger.error(f"Error in description update loop: {e}", exc_info=True)

    def start_streaming(self, webcam_url: str):
        if not self.stream_url:
            logger.error("No stream URL available")
            return False

        # Check if FFmpeg is available
        if not self._check_ffmpeg_available():
            logger.error("FFmpeg not found! Please install FFmpeg:")
            logger.error("  Windows: Download from https://ffmpeg.org/download.html")
            logger.error("  Windows: Add FFmpeg bin folder to your PATH")
            logger.error("  macOS: brew install ffmpeg")
            logger.error("  Linux: sudo apt-get install ffmpeg")
            return False

        try:
            resolution: str = self.config.get("stream_resolution") or "1280x720"
            fps: int = self.config.get("stream_fps") or 30
            bitrate: str = self.config.get("stream_bitrate") or "4000k"

            cmd = [
                "ffmpeg",
                "-re",
                "-thread_queue_size",
                "1024",
                "-f",
                "mjpeg",
                "-i",
                webcam_url,
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-threads",
                "4",
                "-tune",
                "zerolatency",
                "-b:v",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                "1500k",
                "-pix_fmt",
                "yuv420p",
                "-g",
                str(fps * 2),
                "-r",
                str(fps),
                "-vsync",
                "cfr",
                "-s",
                resolution,
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-shortest",
                "-f",
                "flv",
                self.stream_url,
            ]

            logger.info(f"Starting FFmpeg stream: {' '.join(cmd)}")

            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True,
            )

            self._start_ffmpeg_stderr_logger()

            time.sleep(5)
            if self.ffmpeg_process.poll() is not None:
                logger.error("FFmpeg failed to start (process exited)")
                return False

            if self.live_stream and self.live_broadcast:
                stream_id = self.live_stream["id"]
                broadcast_id = self.live_broadcast["id"]

                if not self._wait_for_stream_active(stream_id, timeout=60):
                    logger.warning(
                        "Stream did not become active within 60s, continuing anyway"
                    )
                    logger.info(
                        "Stream may still become active - health check will monitor"
                    )

                if not self._transition_broadcast(broadcast_id, "testing"):
                    logger.error("Failed to transition to testing state")
                    return False

                time.sleep(10)

                live_success = False
                for attempt in range(10):
                    if self._transition_broadcast(broadcast_id, "live"):
                        live_success = True
                        break
                    logger.warning(
                        f"Transition to live failed (attempt {attempt + 1}/10)"
                    )
                    time.sleep(5)

                if not live_success:
                    logger.warning(
                        "Failed to transition to live state after all retries"
                    )
                    logger.info("Stream is running but may not be publicly visible")

            self.is_streaming = True
            self._start_health_monitor()
            self._start_ffmpeg_monitor()
            logger.info("Live streaming started")
            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False

    def _ffmpeg_monitor_loop(self):
        """Monitor FFmpeg process and log if it dies unexpectedly."""
        logger.info("FFmpeg monitor started")
        while self.is_streaming:
            time.sleep(5)
            if not self.is_streaming:
                break
            if self.ffmpeg_process and self.ffmpeg_process.poll() is not None:
                exit_code = self.ffmpeg_process.poll()
                logger.error(
                    f"FFmpeg process died unexpectedly with exit code: {exit_code}"
                )
                if self.ffmpeg_process.stderr:
                    try:
                        stderr_output = self.ffmpeg_process.stderr.read()
                        if stderr_output:
                            logger.error(
                                f"FFmpeg stderr: {stderr_output[-1000:]}"
                            )  # Last 1000 chars
                    except:
                        pass
                self.is_streaming = False
                break
        logger.info("FFmpeg monitor stopped")

    def _start_ffmpeg_monitor(self):
        self._ffmpeg_monitor_thread = threading.Thread(target=self._ffmpeg_monitor_loop)
        self._ffmpeg_monitor_thread.daemon = True
        self._ffmpeg_monitor_thread.start()

    def _start_ffmpeg_stderr_logger(self):
        def log_stderr():
            if not self.ffmpeg_process or not self.ffmpeg_process.stderr:
                return
            try:
                for line in iter(self.ffmpeg_process.stderr.readline, ""):
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        if "error" in line.lower() or "failed" in line.lower():
                            logger.error(f"FFmpeg: {line}")
                        elif "warning" in line.lower():
                            logger.warning(f"FFmpeg: {line}")
                        else:
                            logger.debug(f"FFmpeg: {line}")
            except Exception as e:
                logger.debug(f"FFmpeg stderr logger exited: {e}")

        stderr_thread = threading.Thread(target=log_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()

    def start_description_updates(self, get_print_stats_callback):
        """Start periodic updates of broadcast description with live stats."""
        logger.info(
            f"start_description_updates called with callback: {get_print_stats_callback}"
        )
        if not get_print_stats_callback:
            logger.error("No callback provided for description updates")
            return
        logger.info(
            f"display_title: {self.display_title}, is_streaming: {self.is_streaming}"
        )
        self._description_update_thread = threading.Thread(
            target=self._description_update_loop, args=(get_print_stats_callback,)
        )
        self._description_update_thread.daemon = True
        self._description_update_thread.start()
        logger.info("Started broadcast description updates (15s interval)")

    def stop_streaming(self):
        import traceback

        logger.warning(f"stop_streaming() called from:\n{traceback.format_stack()[-3]}")
        try:
            if self.live_broadcast:
                self._transition_broadcast(self.live_broadcast["id"], "complete")

            if self.ffmpeg_process:
                logger.info("Stopping FFmpeg...")
                self.ffmpeg_process.terminate()
                try:
                    self.ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.ffmpeg_process.kill()
                    self.ffmpeg_process.wait()
                self.ffmpeg_process = None

            self.is_streaming = False
            logger.info("Live streaming stopped")

        except Exception as e:
            logger.error(f"Error stopping stream: {e}")

    def get_watch_url(self) -> Optional[str]:
        if self.live_broadcast:
            broadcast_id = self.live_broadcast["id"]
            return f"https://youtube.com/watch?v={broadcast_id}"
        return None


class YouTubeUploader:
    def __init__(self, config: Config, youtube_service):
        self.config = config
        self.youtube = youtube_service

    def upload_video(
        self, video_path: str, title: str, description: Optional[str] = None
    ) -> Optional[str]:
        try:
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return None

            if not description:
                description = f"3D Print Timelapse: {title}\n\nPrinted on Creality K1 Max with Klipper"

            tags = ["3D printing", "timelapse", "klipper", "creality", "k1 max"]
            category_id = self.config.get("youtube_category_id", "28")
            privacy = self.config.get("video_privacy", "private")

            body = {
                "snippet": {
                    "title": f"Timelapse: {title}",
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id,
                },
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
            }

            logger.info(f"Uploading video: {video_path}")
            logger.info(f"Title: {body['snippet']['title']}")
            logger.info(f"Privacy: {privacy}")

            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

            request = self.youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response["id"]
            video_url = f"https://youtube.com/watch?v={video_id}"

            logger.info(f"Video uploaded successfully: {video_url}")
            return video_url

        except HttpError as e:
            logger.error(f"YouTube API error during upload: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload video: {e}")
            return None


class SpoolUp:
    def __init__(self, config_file: str = "config.json"):
        self.config = Config(config_file)
        self.moonraker = None
        self.youtube = None
        self.streamer = None
        self.uploader = None
        self.print_start_time = None
        self.timelapse_file = None

    def load_youtube_credentials(self) -> bool:
        """Load existing YouTube credentials from token file.

        This runtime version only loads existing tokens, it does NOT
        perform OAuth flow. Authentication must be done separately
        using spoolup-auth on a PC/Mac.
        """
        creds = None
        token_file: str = self.config.get("token_file") or "youtube_token.json"

        if not os.path.exists(token_file):
            logger.error(f"Token file not found: {token_file}")
            logger.error("Please authenticate using spoolup-auth on your PC/Mac")
            logger.error(f"Then copy the token file to: {token_file}")
            return False

        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.info("Loaded existing YouTube credentials")
        except Exception as e:
            logger.error(f"Failed to load token: {e}")
            return False

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Refreshed YouTube credentials")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    logger.error("Please re-authenticate using spoolup-auth")
                    return False
            else:
                logger.error("Credentials are invalid or expired")
                logger.error("Please re-authenticate using spoolup-auth")
                return False

        try:
            disable_ssl = self.config.get("disable_ssl_verify", False)
            if disable_ssl:
                if not HAS_AUTH_HTTP:
                    logger.error(
                        "disable_ssl_verify requires google-auth-httplib2 package"
                    )
                    if _AuthHttpImportError:
                        logger.error(f"Import error: {_AuthHttpImportError}")
                    logger.error("Install it with: pip install google-auth-httplib2")
                    return False

                logger.warning(
                    "SSL verification disabled - using unverified HTTPS context"
                )
                # Create custom SSL context that disables verification
                import ssl as ssl_module

                original_create_default_context = ssl_module.create_default_context

                def patched_create_default_context(*args, **kwargs):
                    context = original_create_default_context(*args, **kwargs)
                    context.check_hostname = False
                    context.verify_mode = ssl_module.CERT_NONE
                    return context

                ssl_module.create_default_context = patched_create_default_context

                http = httplib2.Http(disable_ssl_certificate_validation=True)
                authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)  # type: ignore
                self.youtube = build("youtube", "v3", http=authorized_http)
            else:
                self.youtube = build("youtube", "v3", credentials=creds)

            if self.config.get("enable_live_stream", True):
                self.streamer = YouTubeStreamer(self.config, self.youtube)
            if self.config.get("enable_timelapse_upload", True):
                self.uploader = YouTubeUploader(self.config, self.youtube)

            return True

        except Exception as e:
            logger.error(f"Failed to build YouTube service: {e}")
            logger.error(
                "If you see SSL errors, try setting 'disable_ssl_verify': true in config.json"
            )
            return False

    def on_print_started(self, filename: str):
        self.print_start_time = datetime.now(timezone.utc)
        logger.info(f"Print started at {self.print_start_time}")

        if self.config.get("enable_live_stream", True) and self.streamer:
            # Fetch print statistics for broadcast description
            print_stats = {}
            if self.moonraker:
                print_stats = self.moonraker.get_print_stats()
                logger.info(f"Fetched print stats: {print_stats}")

            if self.streamer.is_streaming:
                logger.info("Stream already active, skipping duplicate creation")
                return

            if self.streamer.create_live_stream(filename, print_stats):
                webcam_url: str = (
                    self.config.get("webcam_url")
                    or "http://localhost:8080/?action=stream"
                )
                if self.streamer.start_streaming(webcam_url):
                    watch_url = self.streamer.get_watch_url()
                    if watch_url:
                        logger.info(f"Live stream URL: {watch_url}")
                        self._send_notification(f"Live stream started: {watch_url}")
                    # Start periodic description updates with live stats
                    if self.moonraker:
                        logger.info("About to start description updates...")
                        self.streamer.start_description_updates(
                            self.moonraker.get_print_stats
                        )
                        logger.info("Description updates initiated")

    def on_print_completed(self, filename: str):
        logger.info("Print completed")

        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.is_streaming:
                self.streamer.stop_streaming()

        if self.config.get("enable_timelapse_upload", True) and self.uploader:
            timelapse_path = self._find_timelapse(filename)
            if timelapse_path:
                logger.info("Waiting for timelapse to be finalized...")
                time.sleep(10)

                video_url = self.uploader.upload_video(
                    timelapse_path,
                    filename,
                    description=self._generate_description(filename),
                )

                if video_url:
                    logger.info(f"Timelapse uploaded: {video_url}")
                    self._send_notification(f"Timelapse uploaded: {video_url}")

    def on_print_cancelled(self, filename: str):
        logger.info("Print cancelled")

        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.is_streaming:
                self.streamer.stop_streaming()

    def _find_timelapse(self, filename: str) -> Optional[str]:
        timelapse_mode = self.config.get("timelapse_mode", "local")

        if timelapse_mode == "remote":
            return self._download_remote_timelapse(filename)

        # Local mode
        timelapse_dir = self.config.get("timelapse_dir")

        if not timelapse_dir or not os.path.isdir(timelapse_dir):
            logger.warning(f"Timelapse directory not found: {timelapse_dir}")
            return None

        base_name = os.path.splitext(filename)[0]

        for ext in [".mp4", ".mkv", ".avi"]:
            timelapse_path = os.path.join(timelapse_dir, f"{base_name}{ext}")
            if os.path.exists(timelapse_path):
                return timelapse_path

            for f in os.listdir(timelapse_dir):
                if f.startswith(base_name) and f.endswith(ext):
                    return os.path.join(timelapse_dir, f)

        files = [
            os.path.join(timelapse_dir, f)
            for f in os.listdir(timelapse_dir)
            if f.endswith((".mp4", ".mkv", ".avi"))
        ]

        if files:
            most_recent = max(files, key=os.path.getmtime)
            if time.time() - os.path.getmtime(most_recent) < 3600:
                return most_recent

        logger.warning(f"Timelapse file not found for: {filename}")
        return None

    def _download_remote_timelapse(self, filename: str) -> Optional[str]:
        """Download timelapse from remote printer via Moonraker API."""
        printer_ip = self.config.get("printer_ip")
        if not printer_ip:
            logger.error("printer_ip not configured for remote timelapse mode")
            return None

        base_name = os.path.splitext(filename)[0]

        try:
            # List timelapse files from printer
            list_url = f"http://{printer_ip}:4409/server/files/list?root=timelapse"
            logger.info(f"Fetching timelapse list from: {list_url}")

            response = requests.get(list_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            files = data.get("result", [])
            if not files:
                logger.warning("No timelapse files found on printer")
                return None

            # Find matching timelapse file
            timelapse_filename = None
            for file_info in files:
                file_name = file_info.get("filename", "")
                if file_name.startswith(base_name) and file_name.endswith(
                    (".mp4", ".mkv", ".avi")
                ):
                    timelapse_filename = file_name
                    break

            if not timelapse_filename:
                logger.warning(f"No timelapse found for print: {filename}")
                return None

            # Download the timelapse file
            download_url = (
                f"http://{printer_ip}:7125/server/files/timelapse/{timelapse_filename}"
            )
            logger.info(f"Downloading timelapse: {download_url}")

            # Create temp directory for downloaded file
            temp_dir = tempfile.gettempdir()
            local_path = os.path.join(temp_dir, timelapse_filename)

            # Download with progress
            response = requests.get(download_url, stream=True, timeout=300)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (1024 * 1024) == 0:
                            progress = (downloaded / total_size) * 100
                            logger.info(f"Download progress: {progress:.1f}%")

            logger.info(f"Timelapse downloaded to: {local_path}")
            return local_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download timelapse from printer: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading timelapse: {e}")
            return None

    def _generate_description(self, filename: str) -> str:
        duration = "Unknown"
        if self.print_start_time:
            duration_str = str(datetime.now() - self.print_start_time).split(".")[0]
            duration = duration_str

        return f"""3D Print Timelapse: {filename}

Printer: Creality K1 Max
Firmware: Klipper
Print Duration: {duration}

This timelapse was automatically generated using Moonraker Timelapse plugin and uploaded by SpoolUp.

#3DPrinting #Klipper #Timelapse #CrealityK1Max
"""

    def _send_notification(self, message: str):
        try:
            response = requests.post(
                f"{self.config.get('moonraker_url')}/server/info",
                json={"message": message},
            )
            logger.info(f"Notification sent: {message}")
        except:
            pass

    def run(self):
        logger.info("=" * 60)
        logger.info("SpoolUp starting...")
        logger.info("=" * 60)

        if not self.load_youtube_credentials():
            logger.error("YouTube credentials not available. Exiting.")
            logger.error("Please authenticate using spoolup-auth on your PC/Mac")
            return 1

        moonraker_url: str = self.config.get("moonraker_url") or "http://localhost:7125"
        self.moonraker = MoonrakerClient(moonraker_url)

        original_on_start = self.moonraker.on_print_started
        original_on_complete = self.moonraker.on_print_completed
        original_on_cancel = self.moonraker.on_print_cancelled

        def on_start(filename):
            original_on_start(filename)
            self.on_print_started(filename)

        def on_complete(filename):
            original_on_complete(filename)
            self.on_print_completed(filename)

        def on_cancel(filename):
            original_on_cancel(filename)
            self.on_print_cancelled(filename)

        self.moonraker.on_print_started = on_start
        self.moonraker.on_print_completed = on_complete
        self.moonraker.on_print_cancelled = on_cancel

        if not self.moonraker.connect_websocket():
            logger.error("Failed to connect to Moonraker. Exiting.")
            return 1

        logger.info("Connected to Moonraker. Monitoring for print events...")
        logger.info("Press Ctrl+C to exit")

        # Wait for subscription to be confirmed (initial state will come via WebSocket)
        logger.info("Waiting for WebSocket subscription confirmation...")
        timeout = 10
        start = time.time()
        while self.moonraker._subscription_pending and time.time() - start < timeout:
            time.sleep(0.1)

        if self.moonraker._subscription_pending:
            logger.warning("Subscription confirmation timeout - proceeding anyway")
        else:
            logger.info(
                "WebSocket subscription confirmed, initial state should be received"
            )
            # Give a moment for the initial status update to be processed
            time.sleep(0.5)

        # Check if already printing when application starts
        logger.info("Checking current print status...")
        print_status = self.moonraker.get_print_status()
        current_state = print_status.get("state", "unknown")
        logger.info(f"HTTP API print state: {current_state}")
        logger.info(f"WebSocket print state: {self.moonraker.print_state}")

        # Use WebSocket state if HTTP returns unknown (more reliable)
        effective_state = current_state
        if current_state == "unknown" and self.moonraker.print_state != "unknown":
            effective_state = self.moonraker.print_state
            logger.info(f"Using WebSocket state instead of HTTP: {effective_state}")

        if effective_state == "printing":
            filename = (
                self.moonraker.current_file
                or print_status.get("filename")
                or "3D Print"
            )
            logger.info(f"Print already in progress: {filename}")
            if self.moonraker._initial_state_handled:
                logger.info(
                    "WebSocket already handled print start, skipping HTTP API trigger"
                )
            else:
                self.moonraker.print_state = "printing"
                self.moonraker.current_file = filename
                self.moonraker._initial_state_handled = True
                self.on_print_started(filename)
        elif effective_state and effective_state != "unknown":
            logger.info(f"Print not active, current state: {effective_state}")
            self.moonraker.print_state = effective_state

        reconnect_thread = self.moonraker.start_reconnection_loop()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if self.streamer and self.streamer.is_streaming:
                self.streamer.stop_streaming()
            if self.moonraker:
                self.moonraker.disconnect()

        return 0


def main():
    parser = argparse.ArgumentParser(
        description="SpoolUp - Stream 3D prints live and upload timelapses"
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        help="Path to configuration file (default: config.json)",
    )

    args = parser.parse_args()

    app = SpoolUp(args.config)
    return app.run()
