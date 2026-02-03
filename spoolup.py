#!/usr/bin/env python3
"""
SpoolUp
A Python script for Creality K1 Max (or any Klipper-based printer) to:
1. Stream live video to YouTube when printing starts
2. Upload timelapse videos to YouTube as drafts when printing completes

Requirements:
    - Python 3.7+
    - Klipper with Moonraker API
    - YouTube Data API v3 credentials
    - FFmpeg (for streaming)
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
import requests
import websocket
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Configuration
SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/spoolup.log"),
    ],
)
logger = logging.getLogger(__name__)


class Config:
    """Configuration manager"""

    DEFAULTS = {
        "moonraker_url": "http://localhost:7125",
        "webcam_url": "http://localhost:8080/?action=stream",
        "timelapse_dir": "/home/user/printer_data/timelapse",
        "client_secrets_file": "client_secrets.json",
        "token_file": "youtube_token.json",
        "stream_resolution": "1280x720",
        "stream_fps": 30,
        "stream_bitrate": "4000k",
        "youtube_category_id": "28",  # Science & Technology
        "video_privacy": "private",  # private, unlisted, public
        "enable_live_stream": True,
        "enable_timelapse_upload": True,
        "retry_attempts": 3,
        "retry_delay": 5,
    }

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.values = self.DEFAULTS.copy()
        self.load()

    def load(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.values.update(json.load(f))
                logger.info(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

    def save(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.values, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.values.get(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.values[key] = value


class MoonrakerClient:
    """Client for Moonraker API (Klipper)"""

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

    def connect_websocket(self):
        """Connect to Moonraker WebSocket"""
        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            logger.info(f"Connecting to Moonraker WebSocket at {self.ws_url}")

            # Run WebSocket in a separate thread
            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()

            # Wait for connection
            timeout = 10
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)

            return self.connected

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False

    def _on_open(self, ws):
        """WebSocket connection opened"""
        logger.info("Moonraker WebSocket connected")
        self.connected = True

        # Subscribe to printer objects
        self._send_jsonrpc(
            "printer.objects.subscribe",
            {"objects": {"print_stats": None, "virtual_sdcard": None}},
        )

    def _on_message(self, ws, message):
        """Handle WebSocket message"""
        try:
            data = json.loads(message)

            # Handle notifications
            if "method" in data:
                method = data["method"]
                params = data.get("params", [])

                if method == "notify_status_update":
                    self._handle_status_update(params[0] if params else {})

            # Handle responses
            elif "id" in data and data["id"] in self.callbacks:
                callback = self.callbacks.pop(data["id"])
                callback(data.get("result"), data.get("error"))

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        """WebSocket error"""
        logger.error(f"WebSocket error: {error}")
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        logger.info("Moonraker WebSocket disconnected")
        self.connected = False

    def _send_jsonrpc(self, method: str, params: Optional[dict] = None) -> int:
        """Send JSON-RPC message"""
        self.message_id += 1
        msg_id = self.message_id

        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": msg_id}
        if params is not None:
            message["params"] = params

        if self.ws and self.connected:
            self.ws.send(json.dumps(message))

        return msg_id

    def _handle_status_update(self, status: dict):
        """Handle status update from printer"""
        if "print_stats" in status:
            stats = status["print_stats"]

            if "state" in stats:
                new_state = stats["state"]
                if new_state != self.print_state:
                    old_state = self.print_state
                    self.print_state = new_state
                    logger.info(f"Print state changed: {old_state} -> {new_state}")

                    # Trigger callbacks based on state
                    if new_state == "printing" and old_state != "printing":
                        self.on_print_started(stats.get("filename"))
                    elif new_state == "complete" and old_state == "printing":
                        self.on_print_completed(stats.get("filename"))
                    elif new_state == "cancelled" and old_state == "printing":
                        self.on_print_cancelled(stats.get("filename"))

            if "filename" in stats:
                self.current_file = stats["filename"]

    def on_print_started(self, filename: str):
        """Override this method to handle print start"""
        logger.info(f"Print started: {filename}")

    def on_print_completed(self, filename: str):
        """Override this method to handle print complete"""
        logger.info(f"Print completed: {filename}")

    def on_print_cancelled(self, filename: str):
        """Override this method to handle print cancelled"""
        logger.info(f"Print cancelled: {filename}")

    def get_printer_info(self) -> dict:
        """Get printer information via REST API"""
        try:
            response = requests.get(f"{self.base_url}/printer/info")
            response.raise_for_status()
            return response.json().get("result", {})
        except Exception as e:
            logger.error(f"Failed to get printer info: {e}")
            return {}

    def get_timelapse_config(self) -> dict:
        """Get timelapse configuration from Moonraker"""
        try:
            response = requests.get(f"{self.base_url}/server/timelapse/settings")
            response.raise_for_status()
            return response.json().get("result", {})
        except Exception as e:
            logger.error(f"Failed to get timelapse config: {e}")
            return {}

    def disconnect(self):
        """Disconnect WebSocket"""
        if self.ws:
            self.ws.close()


class YouTubeStreamer:
    """YouTube Live Streaming handler"""

    def __init__(self, config: Config, youtube_service):
        self.config = config
        self.youtube = youtube_service
        self.ffmpeg_process = None
        self.live_broadcast = None
        self.live_stream = None
        self.stream_url = None
        self.is_streaming = False

    def create_live_stream(self, title: str) -> bool:
        """Create a new YouTube live stream"""
        try:
            # Create live stream
            stream_insert_data = {
                "snippet": {
                    "title": f"Live Stream - {title}",
                },
                "cdn": {
                    "format": "1080p",
                    "ingestionType": "rtmp",
                    "resolution": "1080p",
                    "frameRate": "30fps",
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

            # Create live broadcast
            start_time = datetime.utcnow()
            end_time = start_time + timedelta(hours=24)

            broadcast_insert_data = {
                "snippet": {
                    "title": f"3D Printing: {title}",
                    "description": f"Live stream of 3D print: {title}",
                    "scheduledStartTime": start_time.isoformat() + "Z",
                    "scheduledEndTime": end_time.isoformat() + "Z",
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
                    "enableAutoStart": True,
                    "enableAutoStop": True,
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

            # Bind stream to broadcast
            self.youtube.liveBroadcasts().bind(
                part="id,contentDetails", id=broadcast_id, streamId=stream_id
            ).execute()

            logger.info("Stream bound to broadcast")

            # Transition to testing
            self._transition_broadcast(broadcast_id, "testing")

            return True

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create live stream: {e}")
            return False

    def _transition_broadcast(self, broadcast_id: str, status: str):
        """Transition broadcast status"""
        try:
            self.youtube.liveBroadcasts().transition(
                broadcastId=broadcast_id, part="status", broadcastStatus=status
            ).execute()
            logger.info(f"Broadcast transitioned to: {status}")
        except Exception as e:
            logger.error(f"Failed to transition broadcast: {e}")

    def start_streaming(self, webcam_url: str):
        """Start streaming webcam feed to YouTube"""
        if not self.stream_url:
            logger.error("No stream URL available")
            return False

        try:
            resolution: str = self.config.get("stream_resolution") or "1280x720"
            fps: int = self.config.get("stream_fps") or 30
            bitrate: str = self.config.get("stream_bitrate") or "4000k"

            # Build FFmpeg command
            cmd = [
                "ffmpeg",
                "-f",
                "mjpeg",  # Input format
                "-i",
                webcam_url,  # Input source
                "-f",
                "lavfi",
                "-i",
                "anullsrc",  # Silent audio
                "-c:v",
                "libx264",  # Video codec
                "-preset",
                "veryfast",  # Encoding speed
                "-tune",
                "zerolatency",  # Low latency
                "-b:v",
                bitrate,  # Video bitrate
                "-maxrate",
                bitrate,
                "-bufsize",
                "8000k",
                "-pix_fmt",
                "yuv420p",  # Pixel format for compatibility
                "-g",
                str(fps * 2),  # GOP size
                "-r",
                str(fps),  # Frame rate
                "-s",
                resolution,  # Resolution
                "-c:a",
                "aac",  # Audio codec
                "-b:a",
                "128k",  # Audio bitrate
                "-ar",
                "44100",  # Audio sample rate
                "-f",
                "flv",  # Output format
                self.stream_url,  # RTMP destination
            ]

            logger.info(f"Starting FFmpeg stream: {' '.join(cmd)}")

            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True,
            )

            # Wait a moment and check if process is running
            time.sleep(2)
            if self.ffmpeg_process.poll() is not None:
                if self.ffmpeg_process.stderr:
                    stderr = self.ffmpeg_process.stderr.read()
                    logger.error(f"FFmpeg failed to start: {stderr}")
                else:
                    logger.error("FFmpeg failed to start")
                return False

            # Transition broadcast to live
            if self.live_broadcast:
                self._transition_broadcast(self.live_broadcast["id"], "live")

            self.is_streaming = True
            logger.info("Live streaming started")
            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False

    def stop_streaming(self):
        """Stop the live stream"""
        try:
            # Transition broadcast to complete
            if self.live_broadcast:
                self._transition_broadcast(self.live_broadcast["id"], "complete")

            # Stop FFmpeg
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
        """Get the YouTube watch URL for the live stream"""
        if self.live_broadcast:
            broadcast_id = self.live_broadcast["id"]
            return f"https://youtube.com/watch?v={broadcast_id}"
        return None


class YouTubeUploader:
    """YouTube video upload handler for timelapse"""

    def __init__(self, config: Config, youtube_service):
        self.config = config
        self.youtube = youtube_service

    def upload_video(
        self, video_path: str, title: str, description: Optional[str] = None
    ) -> Optional[str]:
        """Upload a video to YouTube as draft"""
        try:
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                return None

            # Generate metadata
            if not description:
                description = f"3D Print Timelapse: {title}\n\nPrinted on Creality K1 Max with Klipper"

            tags = ["3D printing", "timelapse", "klipper", "creality", "k1 max"]
            category_id = self.config.get(
                "youtube_category_id", "28"
            )  # Science & Technology
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

            # Create media upload
            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

            # Create upload request
            request = self.youtube.videos().insert(
                part="snippet,status", body=body, media_body=media
            )

            # Execute upload with progress
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
    """Main application class"""

    def __init__(self, config_file: str = "config.json"):
        self.config = Config(config_file)
        self.moonraker = None
        self.youtube = None
        self.streamer = None
        self.uploader = None
        self.print_start_time = None
        self.timelapse_file = None

    def authenticate_youtube(self) -> bool:
        """Authenticate with YouTube API"""
        creds = None
        token_file: str = self.config.get("token_file") or "youtube_token.json"
        client_secrets: str = (
            self.config.get("client_secrets_file") or "client_secrets.json"
        )

        # Load existing token
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
                logger.info("Loaded existing YouTube credentials")
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Refreshed YouTube credentials")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    creds = None

            if not creds:
                if not os.path.exists(client_secrets):
                    logger.error(f"Client secrets file not found: {client_secrets}")
                    logger.error(
                        "Please download your client secrets from Google Cloud Console"
                    )
                    return False

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secrets, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                    logger.info("Authenticated with YouTube")
                except Exception as e:
                    logger.error(f"Authentication failed: {e}")
                    return False

            # Save token
            try:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
                logger.info(f"Saved credentials to {token_file}")
            except Exception as e:
                logger.warning(f"Failed to save token: {e}")

        try:
            self.youtube = build("youtube", "v3", credentials=creds)

            # Initialize streamer and uploader
            if self.config.get("enable_live_stream", True):
                self.streamer = YouTubeStreamer(self.config, self.youtube)
            if self.config.get("enable_timelapse_upload", True):
                self.uploader = YouTubeUploader(self.config, self.youtube)

            return True

        except Exception as e:
            logger.error(f"Failed to build YouTube service: {e}")
            return False

    def on_print_started(self, filename: str):
        """Handle print start event"""
        self.print_start_time = datetime.now()
        logger.info(f"Print started at {self.print_start_time}")

        if self.config.get("enable_live_stream", True) and self.streamer:
            # Create live stream
            if self.streamer.create_live_stream(filename):
                # Start streaming
                webcam_url: str = (
                    self.config.get("webcam_url")
                    or "http://localhost:8080/?action=stream"
                )
                if self.streamer.start_streaming(webcam_url):
                    watch_url = self.streamer.get_watch_url()
                    if watch_url:
                        logger.info(f"Live stream URL: {watch_url}")

                        # Send notification to printer (if supported)
                        self._send_notification(f"Live stream started: {watch_url}")

    def on_print_completed(self, filename: str):
        """Handle print complete event"""
        logger.info("Print completed")

        # Stop live stream
        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.is_streaming:
                self.streamer.stop_streaming()

        # Upload timelapse
        if self.config.get("enable_timelapse_upload", True) and self.uploader:
            timelapse_path = self._find_timelapse(filename)
            if timelapse_path:
                # Wait a bit for timelapse to be finalized
                logger.info("Waiting for timelapse to be finalized...")
                time.sleep(10)

                # Upload timelapse
                video_url = self.uploader.upload_video(
                    timelapse_path,
                    filename,
                    description=self._generate_description(filename),
                )

                if video_url:
                    logger.info(f"Timelapse uploaded: {video_url}")
                    self._send_notification(f"Timelapse uploaded: {video_url}")

    def on_print_cancelled(self, filename: str):
        """Handle print cancelled event"""
        logger.info("Print cancelled")

        # Stop live stream
        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.is_streaming:
                self.streamer.stop_streaming()

    def _find_timelapse(self, filename: str) -> Optional[str]:
        """Find timelapse file for the completed print"""
        timelapse_dir = self.config.get("timelapse_dir")

        if not timelapse_dir or not os.path.isdir(timelapse_dir):
            logger.warning(f"Timelapse directory not found: {timelapse_dir}")
            return None

        # Remove extension from filename
        base_name = os.path.splitext(filename)[0]

        # Look for matching timelapse files
        for ext in [".mp4", ".mkv", ".avi"]:
            # Try exact match
            timelapse_path = os.path.join(timelapse_dir, f"{base_name}{ext}")
            if os.path.exists(timelapse_path):
                return timelapse_path

            # Try with timestamp pattern
            for f in os.listdir(timelapse_dir):
                if f.startswith(base_name) and f.endswith(ext):
                    return os.path.join(timelapse_dir, f)

        # If not found, get the most recent timelapse file
        files = [
            os.path.join(timelapse_dir, f)
            for f in os.listdir(timelapse_dir)
            if f.endswith((".mp4", ".mkv", ".avi"))
        ]

        if files:
            most_recent = max(files, key=os.path.getmtime)
            # Check if it's recent enough (within last hour)
            if time.time() - os.path.getmtime(most_recent) < 3600:
                return most_recent

        logger.warning(f"Timelapse file not found for: {filename}")
        return None

    def _generate_description(self, filename: str) -> str:
        """Generate video description"""
        duration = "Unknown"
        if self.print_start_time:
            duration_str = str(datetime.now() - self.print_start_time).split(".")[0]
            duration = duration_str

        description = f"""3D Print Timelapse: {filename}

Printer: Creality K1 Max
Firmware: Klipper
Print Duration: {duration}

This timelapse was automatically generated using Moonraker Timelapse plugin and uploaded by SpoolUp.

#3DPrinting #Klipper #Timelapse #CrealityK1Max
"""
        return description

    def _send_notification(self, message: str):
        """Send notification to printer (via Moonraker)"""
        try:
            # Try to use Moonraker's notification system
            response = requests.post(
                f"{self.config.get('moonraker_url')}/server/info",
                json={"message": message},
            )
            logger.info(f"Notification sent: {message}")
        except:
            pass  # Notifications are optional

    def run(self):
        """Main run loop"""
        logger.info("=" * 60)
        logger.info("SpoolUp starting...")
        logger.info("=" * 60)

        # Authenticate with YouTube
        if not self.authenticate_youtube():
            logger.error("YouTube authentication failed. Exiting.")
            return 1

        # Connect to Moonraker
        moonraker_url: str = self.config.get("moonraker_url") or "http://localhost:7125"
        self.moonraker = MoonrakerClient(moonraker_url)

        # Set up event handlers
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

        # Connect WebSocket
        if not self.moonraker.connect_websocket():
            logger.error("Failed to connect to Moonraker. Exiting.")
            return 1

        logger.info("Connected to Moonraker. Monitoring for print events...")
        logger.info("Press Ctrl+C to exit")

        try:
            while True:
                if not self.moonraker.connected:
                    logger.warning("WebSocket disconnected. Reconnecting...")
                    if not self.moonraker.connect_websocket():
                        time.sleep(5)
                        continue
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if self.streamer and self.streamer.is_streaming:
                self.streamer.stop_streaming()
            if self.moonraker:
                self.moonraker.disconnect()

        return 0


def create_sample_config():
    """Create a sample configuration file"""
    config = {
        "moonraker_url": "http://localhost:7125",
        "webcam_url": "http://localhost:8080/?action=stream",
        "timelapse_dir": "/home/user/printer_data/timelapse",
        "client_secrets_file": "client_secrets.json",
        "token_file": "youtube_token.json",
        "stream_resolution": "1280x720",
        "stream_fps": 30,
        "stream_bitrate": "4000k",
        "stream_privacy": "unlisted",
        "youtube_category_id": "28",
        "video_privacy": "private",
        "enable_live_stream": True,
        "enable_timelapse_upload": True,
        "retry_attempts": 3,
        "retry_delay": 5,
    }

    with open("config.json.sample", "w") as f:
        json.dump(config, f, indent=2)

    print("Sample configuration created: config.json.sample")
    print("Copy it to config.json and edit the values for your setup")


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
    parser.add_argument(
        "--create-config",
        action="store_true",
        help="Create a sample configuration file",
    )
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Only authenticate with YouTube and exit",
    )

    args = parser.parse_args()

    if args.create_config:
        create_sample_config()
        return 0

    app = SpoolUp(args.config)

    if args.auth_only:
        if app.authenticate_youtube():
            logger.info("Authentication successful!")
            return 0
        else:
            logger.error("Authentication failed!")
            return 1

    return app.run()


if __name__ == "__main__":
    sys.exit(main())
