#!/usr/bin/env python3
"""
SpoolUp Runtime Module
Main application for streaming 3D prints to YouTube
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
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

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
    DEFAULTS = {
        "moonraker_url": "http://localhost:7125",
        "webcam_url": "http://localhost:8080/?action=stream",
        "timelapse_dir": "/home/user/printer_data/timelapse",
        "client_secrets_file": "client_secrets.json",
        "token_file": "youtube_token.json",
        "stream_resolution": "1280x720",
        "stream_fps": 30,
        "stream_bitrate": "4000k",
        "youtube_category_id": "28",
        "video_privacy": "private",
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

    def connect_websocket(self):
        try:
            self.ws = websocket.WebSocketApp(
                self.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            logger.info(f"Connecting to Moonraker WebSocket at {self.ws_url}")

            ws_thread = threading.Thread(target=self.ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()

            timeout = 10
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)

            return self.connected

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False

    def _on_open(self, ws):
        logger.info("Moonraker WebSocket connected")
        self.connected = True
        self._send_jsonrpc(
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

            elif "id" in data and data["id"] in self.callbacks:
                callback = self.callbacks.pop(data["id"])
                callback(data.get("result"), data.get("error"))

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("Moonraker WebSocket disconnected")
        self.connected = False

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
                        self.on_print_started(stats.get("filename"))
                    elif new_state == "complete" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
                        self.on_print_completed(stats.get("filename"))
                    elif new_state == "cancelled" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
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

    def disconnect(self):
        if self.ws:
            self.ws.close()


class YouTubeStreamer:
    def __init__(self, config: Config, youtube_service):
        self.config = config
        self.youtube = youtube_service
        self.ffmpeg_process = None
        self.live_broadcast = None
        self.live_stream = None
        self.stream_url = None
        self.is_streaming = False

    def create_live_stream(self, title: str) -> bool:
        try:
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

            self.youtube.liveBroadcasts().bind(
                part="id,contentDetails", id=broadcast_id, streamId=stream_id
            ).execute()

            logger.info("Stream bound to broadcast")
            self._transition_broadcast(broadcast_id, "testing")

            return True

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to create live stream: {e}")
            return False

    def _transition_broadcast(self, broadcast_id: str, status: str):
        try:
            broadcast = (
                self.youtube.liveBroadcasts()
                .list(part="status", id=broadcast_id)
                .execute()
            )

            if not broadcast.get("items"):
                logger.warning(f"Broadcast {broadcast_id} not found")
                return

            current_status = broadcast["items"][0]["status"]["lifeCycleStatus"]

            valid_transitions = {
                "created": ["testing"],
                "testing": ["live"],
                "live": ["complete"],
            }

            if current_status == status:
                logger.info(f"Broadcast already in '{status}' state")
                return

            if status not in valid_transitions.get(current_status, []):
                logger.warning(
                    f"Cannot transition from '{current_status}' to '{status}'"
                )
                return

            self.youtube.liveBroadcasts().transition(
                id=broadcast_id, part="status", broadcastStatus=status
            ).execute()
            logger.info(f"Broadcast transitioned from '{current_status}' to '{status}'")
        except Exception as e:
            logger.error(f"Failed to transition broadcast: {e}")

    def start_streaming(self, webcam_url: str):
        if not self.stream_url:
            logger.error("No stream URL available")
            return False

        try:
            resolution: str = self.config.get("stream_resolution") or "1280x720"
            fps: int = self.config.get("stream_fps") or 30
            bitrate: str = self.config.get("stream_bitrate") or "4000k"

            cmd = [
                "ffmpeg",
                "-f",
                "mjpeg",
                "-i",
                webcam_url,
                "-f",
                "lavfi",
                "-i",
                "anullsrc",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-b:v",
                bitrate,
                "-maxrate",
                bitrate,
                "-bufsize",
                "8000k",
                "-pix_fmt",
                "yuv420p",
                "-g",
                str(fps * 2),
                "-r",
                str(fps),
                "-s",
                resolution,
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-f",
                "flv",
                self.stream_url,
            ]

            logger.info(f"Starting FFmpeg stream: {' '.join(cmd)}")

            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
                universal_newlines=True,
            )

            time.sleep(2)
            if self.ffmpeg_process.poll() is not None:
                if self.ffmpeg_process.stderr:
                    stderr = self.ffmpeg_process.stderr.read()
                    logger.error(f"FFmpeg failed to start: {stderr}")
                else:
                    logger.error("FFmpeg failed to start")
                return False

            if self.live_broadcast:
                self._transition_broadcast(self.live_broadcast["id"], "live")

            self.is_streaming = True
            logger.info("Live streaming started")
            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False

    def stop_streaming(self):
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
            self.youtube = build("youtube", "v3", credentials=creds)

            if self.config.get("enable_live_stream", True):
                self.streamer = YouTubeStreamer(self.config, self.youtube)
            if self.config.get("enable_timelapse_upload", True):
                self.uploader = YouTubeUploader(self.config, self.youtube)

            return True

        except Exception as e:
            logger.error(f"Failed to build YouTube service: {e}")
            return False

    def on_print_started(self, filename: str):
        self.print_start_time = datetime.now()
        logger.info(f"Print started at {self.print_start_time}")

        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.create_live_stream(filename):
                webcam_url: str = (
                    self.config.get("webcam_url")
                    or "http://localhost:8080/?action=stream"
                )
                if self.streamer.start_streaming(webcam_url):
                    watch_url = self.streamer.get_watch_url()
                    if watch_url:
                        logger.info(f"Live stream URL: {watch_url}")
                        self._send_notification(f"Live stream started: {watch_url}")

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
