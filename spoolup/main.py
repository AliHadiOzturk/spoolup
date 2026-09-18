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
import re
import subprocess
import threading
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Callable, List

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

from spoolup.frame_pump import FramePump

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
        "stream_fps": 30,
        "stream_bitrate": "4500k",
        "stream_buffer_size": "9000k",
        "timelapse_mode": "local",
        "printer_ip": "",
        "moonraker_port": "4409",
        "youtube_category_id": "28",
        "video_privacy": "private",
        "stream_privacy": "unlisted",
        "enable_live_stream": True,
        "enable_timelapse_upload": True,
        "retry_attempts": 3,
        "retry_delay": 5,
        "disable_ssl_verify": False,
        "kick_enabled": False,
        "kick_rtmp_url": "rtmp://fa723fc1b91d4.global-media-services.com:1935/live",
        "kick_stream_key": "",
        "kick_channel_url": "https://kick.com/alihadiozturk",
        "ingest_buffer_seconds": 10,
        "dashboard_enabled": True,
        "dashboard_host": "127.0.0.1",
        "dashboard_port": 8007,
        "audio_server_enabled": True,
        "audio_default_volume": 0.8,
        "data_dir": "data",
        "librespot_path": "",
        "spotify_username": "",
        "spotify_password": "",
        "spotify_playlist_uri": "",
        "mainsail_url": "",
        "watchdog_interval": 30,
        "keep_stream_on_error": True,
        "auto_update_enabled": True,
        "auto_update_interval_h": 2,
        "log_file": "data/spoolup.log",
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

    def save(self) -> bool:
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.values, f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value: Any):
        self.values[key] = value

    def set_many(self, values: Dict[str, Any]) -> None:
        self.values.update(values)


def build_dashboard_context(su: "SpoolUp") -> "RuntimeContext":
    """Build the framework-free bridge the dashboard talks through."""
    from spoolup.dashboard.state import RuntimeContext as _RTC

    def _probe_webcam(url: str) -> bool:
        if not url:
            return False
        try:
            resp = requests.get(url, stream=True, timeout=(5, 10))
            if resp.status_code != 200:
                return False
            return bool(next(resp.iter_content(chunk_size=1024), None))
        except Exception:
            return False

    def _probe_moonraker(url: str) -> bool:
        if not url:
            return False
        try:
            probe_url = url.rstrip("/") + "/server/info"
            resp = requests.get(probe_url, timeout=5)
            return resp.ok
        except Exception:
            return False

    return _RTC(
        runtime=su,
        config_get=su.config.get,
        config_keys=list(su.config.values.keys()),
        secret_keys=["kick_stream_key", "spotify_password"],
        config_file=su.config.config_file,
        save_config=lambda values: (
            su.config.set_many(values),
            su.config.save(),
        )[-1],
        test_moonraker=_probe_moonraker,
        test_webcam=_probe_webcam,
    )


class MoonrakerClient:
    def __init__(
        self,
        base_url: str,
        on_error_state: Optional[Callable[[], None]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.on_error_state = on_error_state
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
        self._temperatures: Dict[str, float] = {}
        self._display_progress: float = 0.0

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
            {
                "objects": {
                    "print_stats": None,
                    "virtual_sdcard": None,
                    "toolhead": None,
                    "extruder": None,
                    "heater_bed": None,
                    "display_status": None,
                    "gcode_move": None,
                }
            },
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

            if "filename" in stats:
                self.current_file = stats["filename"]

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
                        filename = self.current_file or stats.get("filename")
                        logger.info(f"Triggering print start callback for: {filename}")
                        self._initial_state_handled = True
                        self.on_print_started(filename)
                    elif new_state == "complete" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
                        self._initial_state_handled = False
                        self.on_print_completed(self.current_file)
                    elif new_state == "cancelled" and old_state in [
                        "printing",
                        "error",
                        "paused",
                    ]:
                        self._initial_state_handled = False
                        self.on_print_cancelled(self.current_file)
                    elif new_state == "error" and old_state == "printing":
                        logger.warning(
                            "Print error detected - stream continuing. Waiting for recovery or completion..."
                        )
                        if self.on_error_state is not None:
                            try:
                                self.on_error_state()
                            except Exception as e:
                                logger.error("on_error_state handler failed: %s", e)

        self._extract_temperatures(status)
        self._extract_display_status(status)

    def _extract_temperatures(self, status: dict):
        temp_keys = [
            "extruder",
            "heater_bed",
            "temperature_sensor chamber_temp",
            "temperature_sensor mcu_temp",
            "temperature_fan chamber_fan",
        ]
        for key in temp_keys:
            if key in status:
                obj = status[key]
                if "temperature" in obj:
                    self._temperatures[key] = obj["temperature"]

    def _extract_display_status(self, status: dict):
        """Extract display_status (progress) from status update."""
        if "display_status" in status:
            display = status["display_status"]
            if "progress" in display:
                self._display_progress = display["progress"]

    def get_temperatures(self) -> Dict[str, float]:
        return self._temperatures.copy()

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
            # Moonraker expects query params as ?object1&object2 (no values)
            # Use list of tuples to ensure proper URL encoding
            query_params = [
                ("print_stats", ""),
                ("virtual_sdcard", ""),
                ("toolhead", ""),
                ("extruder", ""),
                ("heater_bed", ""),
                ("display_status", ""),
                ("temperature_sensor chamber_temp", ""),
                ("temperature_sensor mcu_temp", ""),
                ("temperature_fan chamber_fan", ""),
            ]
            response = requests.get(
                f"{self.base_url}/printer/objects/query",
                params=query_params,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            status = result.get("status", {})

            print_stats = status.get("print_stats", {})
            virtual_sdcard = status.get("virtual_sdcard", {})
            toolhead = status.get("toolhead", {})
            extruder = status.get("extruder", {})
            heater_bed = status.get("heater_bed", {})
            display_status = status.get("display_status", {})

            # File name
            filename = virtual_sdcard.get("filename", "")
            stats["filename"] = filename if filename else "Unknown"

            # Speed and flow from toolhead (may not be available on all printers)
            speed = toolhead.get("speed", 0)
            stats["speed"] = f"{speed:.0f} mm/s" if speed else "N/A"

            # Flow rate in mm³/s (not always exposed by Moonraker)
            flow_rate = toolhead.get("flow_rate", 0)
            if not flow_rate:
                # Try to calculate from extruder position changes if available
                # This is a fallback - actual flow rate may differ
                flow_rate = 0
            stats["flow_rate"] = f"{flow_rate:.1f} mm³/s" if flow_rate else "N/A"

            filament_mm = print_stats.get("filament_used", 0)
            stats["filament_used"] = (
                f"{filament_mm / 1000:.2f} m" if filament_mm else "0.00 m"
            )

            # Layer info - try print_stats.info first, fallback to virtual_sdcard
            print_info = print_stats.get("info", {})
            current_layer = print_info.get("current_layer", 0)
            total_layers = print_info.get("total_layer", 0)
            
            # Fallback to virtual_sdcard if print_stats doesn't have layer data
            if not current_layer and virtual_sdcard:
                current_layer = virtual_sdcard.get("layer", 0)
            if not total_layers and virtual_sdcard:
                total_layers = virtual_sdcard.get("layer_count", 0)
            
            stats["current_layer"] = current_layer if current_layer else 0
            stats["total_layers"] = total_layers if total_layers else 0

            print_duration = print_stats.get("print_duration", 0)
            total_duration = print_stats.get("total_duration", 0)

            def format_duration(seconds: int) -> str:
                """Format seconds to HH:MM:SS, handling durations > 24 hours."""
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                return f"{hours}:{minutes:02d}:{secs:02d}"

            if total_duration:
                stats["total_time"] = format_duration(int(total_duration))
            else:
                stats["total_time"] = "0:00:00"

            # Progress - prefer virtual_sdcard (more accurate), fallback to display_status
            progress = virtual_sdcard.get("progress", 0) or display_status.get("progress", 0)
            if progress > 0 and print_duration > 0:
                estimated_total = print_duration / progress
                remaining = estimated_total - print_duration
                stats["estimate"] = format_duration(int(remaining))

                eta_time = datetime.now() + timedelta(seconds=int(remaining))
                stats["eta"] = eta_time.strftime("%I:%M %p")
            else:
                stats["estimate"] = "Calculating..."
                stats["eta"] = "Calculating..."

            if progress > 0 and print_duration > 0:
                estimated_total = print_duration / progress
                stats["slicer_time"] = format_duration(int(estimated_total))
            else:
                stats["slicer_time"] = "N/A"

            # Store raw progress for description updates
            stats["progress"] = progress

            # Read temperatures directly from query response (more reliable than cached)
            # Extruder
            extruder_temp = extruder.get("temperature", 0)
            extruder_target = extruder.get("target", 0)
            stats["extruder_temp"] = extruder_temp
            stats["extruder_target"] = extruder_target
            stats["extruder_temp_str"] = f"{extruder_temp:.1f}°C" if extruder_temp else "N/A"
            stats["extruder_target_str"] = f"{extruder_target:.0f}°C" if extruder_target else "N/A"

            # Bed
            bed_temp = heater_bed.get("temperature", 0)
            bed_target = heater_bed.get("target", 0)
            stats["bed_temp"] = bed_temp
            stats["bed_target"] = bed_target
            stats["bed_temp_str"] = f"{bed_temp:.1f}°C" if bed_temp else "N/A"
            stats["bed_target_str"] = f"{bed_target:.0f}°C" if bed_target else "N/A"

            # Chamber - try temperature_sensor chamber_temp first, fallback to old name
            chamber_sensor = status.get("temperature_sensor chamber_temp", {})
            if not chamber_sensor:
                chamber_sensor = status.get("temperature_sensor chamber", {})
            chamber_temp = chamber_sensor.get("temperature", 0)
            if not chamber_temp:
                # Fallback to cached temps with both names
                chamber_temp = self._temperatures.get("temperature_sensor chamber_temp", 0) or \
                              self._temperatures.get("temperature_sensor chamber", 0)
            stats["chamber_temp"] = chamber_temp
            stats["chamber_temp_str"] = f"{chamber_temp:.1f}°C" if chamber_temp else "N/A"

            # MCU - try temperature_sensor mcu_temp first, fallback to old name
            mcu_sensor = status.get("temperature_sensor mcu_temp", {})
            if not mcu_sensor:
                mcu_sensor = status.get("temperature_sensor mcu", {})
            mcu_temp = mcu_sensor.get("temperature", 0)
            if not mcu_temp:
                # Fallback to cached temps with both names
                mcu_temp = self._temperatures.get("temperature_sensor mcu_temp", 0) or \
                          self._temperatures.get("temperature_sensor mcu", 0)
            stats["mcu_temp"] = mcu_temp
            stats["mcu_temp_str"] = f"{mcu_temp:.1f}°C" if mcu_temp else "N/A"

            # Chamber fan target (for temperature control)
            chamber_fan = status.get("temperature_fan chamber_fan", {})
            if chamber_fan:
                stats["chamber_target"] = chamber_fan.get("target", 0)
                stats["chamber_fan_speed"] = chamber_fan.get("speed", 0)

        except Exception as e:
            logger.error(f"Failed to get print stats: {e}")

        return stats


class StreamManager:
    """Multi-destination stream manager (YouTube + Kick)."""

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
        self._ffmpeg_monitor_thread = None
        self._description_update_thread = None
        self.frame_pump: Optional[FramePump] = None
        self.encode_speed: Optional[float] = None
        self.audio_server = None
        # Ownership transfer hooks (set by SpoolUp): provider steals the
        # standby AudioServer when spawning; on_kill_audio reclaims it when
        # the pipeline dies (music survives stream stop). When unset, the
        # Task-3 behavior applies: create fresh on spawn, stop() on kill.
        self.audio_server_provider: Optional[Callable] = None
        self.on_kill_audio: Optional[Callable] = None
        self._stopping = False
        self._ffmpeg_died_unexpectedly = False
        # Set by SpoolUp: called when the monitor detects an unexpected ffmpeg
        # death (used to add a dashboard banner).
        self.on_ffmpeg_death: Optional[Callable[[], None]] = None

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

    def _detect_h264_encoder(self) -> str:
        """Detect best available H.264 encoder. Falls back from hardware to software."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            encoders = result.stdout
        except Exception as e:
            logger.warning(f"Could not detect encoders: {e}")
            return "libx264"

        # Priority: Intel QSV > Apple VideoToolbox > Rockchip MPP > NVIDIA NVENC > software
        preferred = [
            ("h264_qsv", "Intel QuickSync"),
            ("h264_videotoolbox", "Apple VideoToolbox"),
            ("h264_rkmpp", "Rockchip MPP"),
            ("h264_nvenc", "NVIDIA NVENC"),
            ("h264_vaapi", "VAAPI"),
            ("h264_amf", "AMD AMF"),
        ]

        for encoder, name in preferred:
            if encoder in encoders:
                logger.info(f"Using hardware encoder: {name} ({encoder})")
                return encoder

        logger.info("Using software encoder: libx264")
        return "libx264"

    @staticmethod
    def _mask_key(key: str) -> str:
        return (key[:4] + "***") if key else "<empty>"

    def _masked_text(self, text: str) -> str:
        """Mask stream keys that may appear inside ffmpeg stderr text."""
        kick_key: str = self.config.get("kick_stream_key") or ""
        if kick_key and kick_key in text:
            text = text.replace(kick_key, self._mask_key(kick_key))
        # Mask any 'streamid=<value>' (SRT URLs may embed the key there)
        text = re.sub(
            r"(streamid=)[^\s&|]+",
            lambda m: m.group(1) + "sk_id***",
            text,
        )
        if self.stream_url:
            stream_key = self.stream_url.rsplit("/", 1)[-1]
            if stream_key and stream_key in text:
                text = text.replace(stream_key, self._mask_key(stream_key))
            if self.stream_url in text:
                text = text.replace(self.stream_url, self._mask_key(self.stream_url))
        return text

    def _log_ffmpeg_command(self, cmd: List[str], label: str) -> None:
        """Log the FFmpeg command with stream keys masked (log-only)."""
        masked_cmd = [self._masked_text(part) for part in cmd]
        logger.info(f"{label}: {' '.join(masked_cmd)}")

    def _build_output_spec(self) -> str:
        """ffmpeg tee muxer spec: all enabled sinks share the single encode.

        RTMP/RTMPS sinks use the FLV muxer; SRT sinks use MPEG-TS (the
        transport SRT carries). Key handling: for `srt://` URLs the stream
        id may already be embedded in `streamid=` (Kick dashboard style) —
        otherwise kick_stream_key is appended as a streamid query param.
        """
        parts = []
        if self.stream_url:
            parts.append("[f=flv:onfail=ignore]%s" % self.stream_url)
        if self.config.get("kick_enabled"):
            kick_key: str = self.config.get("kick_stream_key") or ""
            kick_url: str = self.config.get("kick_rtmp_url") or ""
            kick_url = kick_url.strip()
            srt = kick_url.lower().startswith("srt://")
            ok = bool(kick_url) and (bool(kick_key) or "streamid=" in kick_url)
            if not ok:
                logger.warning(
                    "kick_enabled but kick_stream_key/kick_rtmp_url missing - "
                    "Kick output DISABLED"
                )
            else:
                if srt:
                    url = kick_url
                    if kick_key and "streamid=" not in url:
                        url += ("&" if "?" in url else "?") + "streamid=" + kick_key
                    parts.append("[f=mpegts:onfail=ignore]%s" % url)
                    logger.info(
                        "Kick output enabled (SRT): %s",
                        self._masked_text(url),
                    )
                else:
                    url = "%s/%s" % (kick_url.rstrip("/"), kick_key)
                    parts.append("[f=flv:onfail=ignore]%s" % url)
                    logger.info(
                        "Kick output enabled (RTMP): %s", self._masked_text(url)
                    )
        if not parts:
            raise ValueError(
                "No RTMP outputs configured (stream_url missing and Kick disabled)"
            )
        return "|".join(parts)

    def _build_ffmpeg_cmd(self, webcam_url: str,
                          audio_port: Optional[int] = None) -> List[str]:
        """Build FFmpeg command with optimal settings for YouTube streaming."""
        resolution = self.config.get("stream_resolution") or "1280x720"
        fps: int = self.config.get("stream_fps") or 30
        bitrate: str = self.config.get("stream_bitrate") or "4000k"
        buffer_size: str = self.config.get("stream_buffer_size") or "8000k"
        encoder = self._detect_h264_encoder()

        # Audio input: live PCM feed from AudioServer when available,
        # otherwise the legacy silent source (required by YouTube).
        if audio_port:
            audio_input = [
                "-f", "s16le", "-ar", "44100", "-ac", "2",
                "-i", "tcp://127.0.0.1:%d" % audio_port,
            ]
        else:
            audio_input = [
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ]

        # YouTube prefers 2-second GOP (Group of Pictures)
        gop_size = fps * 2

        # Build encoder-specific options
        video_opts = [
            "-c:v", encoder,
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-minrate", bitrate,
            "-bufsize", buffer_size,
            "-g", str(gop_size),
            "-keyint_min", str(gop_size),
            "-pix_fmt", "yuv420p",
        ]

        # Add encoder-specific flags
        if encoder == "libx264":
            video_opts.extend([
                "-preset", "veryfast",
                "-tune", "zerolatency",
                "-x264-params", f"sc_threshold=0:min-keyint={gop_size}",
            ])
        elif encoder == "h264_qsv":
            # QSV-specific: use CBR mode
            video_opts.extend([
                "-preset", "fast",
            ])
        elif encoder == "h264_nvenc":
            video_opts.extend([
                "-preset", "p4",
                "-tune", "ll",
            ])
        elif encoder == "h264_videotoolbox":
            video_opts.extend([
                "-realtime", "1",
            ])

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-stats",
            # Input: MJPEG frames fed by FramePump over stdin.
            # -framerate MUST match the pump's pacing (stream_fps): the raw
            # mjpeg demuxer assumes 25fps otherwise and the output timeline
            # drifts progressively behind realtime on long prints.
            "-f", "image2pipe",
            "-framerate", str(fps),
            "-c:v", "mjpeg",
            "-i", "pipe:0",
            # Audio input (live AudioServer feed, or silent anullsrc fallback)
            *audio_input,
            # Video filter: enforce framerate, scale, ensure YUV420P for compatibility
            "-filter_complex",
            f"[0:v]fps={fps}:round=down,scale={resolution},format=yuv420p[v]",
            "-map", "[v]",
            "-map", "1:a",
            # Muxer queue: prevent blocking when audio/video sync is temporarily off
            "-max_muxing_queue_size", "1024",
            # Output CFR pacing: prevents the encoder from draining the input queue
            # faster than realtime (burst). Without this, the initial burst empties
            # the buffer before the webcam's deterministic ~9s stall at frame 308,
            # causing a complete output freeze (videoIngestionStarved).
            "-fps_mode", "cfr",
            # Video encoding options
            *video_opts,
            # Audio encoding
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            # Stop when shortest input ends (prevents infinite anullsrc)
            "-shortest",
            # Output format
            "-f", "tee",
            self._build_output_spec(),
        ]

        self._log_ffmpeg_command(cmd, "FFmpeg command")
        return cmd

    def _spawn_pipeline(self, webcam_url: str) -> bool:
        """Start FramePump + ffmpeg (stdin=PIPE). Shared by start/restart."""
        fps: int = self.config.get("stream_fps") or 30
        buffer_seconds: int = self.config.get("ingest_buffer_seconds") or 10

        pump = FramePump(webcam_url, fps, buffer_seconds)
        pump.start()
        if not pump.wait_for_first_frame(timeout=10.0):
            pump.stop()
            return False

        audio_port = None
        if self.config.get("audio_server_enabled", True):
            # Re-entered without _kill_ffmpeg (encoder retry / failed start):
            # reclaim the previously adopted server before making a new one.
            if self.audio_server is not None:
                if self.on_kill_audio is not None:
                    try:
                        self.on_kill_audio(self.audio_server)
                    except Exception as e:
                        logger.error("on_kill_audio failed, stopping server: %s", e)
                        self.audio_server.stop()
                else:
                    self.audio_server.stop()
                self.audio_server = None
            # Adopt the standby server (source/volume configured from the
            # dashboard persist across stream start) or create a fresh one.
            server = None
            if self.audio_server_provider is not None:
                try:
                    server = self.audio_server_provider()
                except Exception as e:
                    logger.error("audio_server_provider failed: %s", e)
                    server = None
            if server is None:
                try:
                    from spoolup.audio_server import AudioServer
                    server = AudioServer(
                        volume=float(self.config.get("audio_default_volume", 0.8) or 0.8)
                    )
                except Exception as e:
                    logger.error("AudioServer init failed, silent audio: %s", e)
                    server = None
            if server is not None:
                try:
                    audio_port = server.start()
                    self.audio_server = server
                except Exception as e:
                    logger.error("AudioServer start failed, silent audio: %s", e)
                    self.audio_server = None
                    audio_port = None
        cmd = self._build_ffmpeg_cmd(webcam_url, audio_port=audio_port)
        self._last_cmd = cmd
        self._last_webcam_url = webcam_url
        self._log_ffmpeg_command(cmd, "Starting FFmpeg stream")
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.frame_pump = pump
        self.ffmpeg_process = process
        self._start_ffmpeg_stderr_logger()

        time.sleep(5)
        if process.poll() is not None:
            self._log_ffmpeg_start_failure(process.poll())
            return self._retry_with_software_encoder(pump)

        try:
            pump.serve(process.stdin.fileno())
        except Exception as e:
            logger.error(f"Could not start frame pacer: {e}")
            process.kill()
            pump.stop()
            self.frame_pump = None
            self.ffmpeg_process = None
            return False
        return True

    def _log_ffmpeg_start_failure(self, exit_code: Optional[int]) -> None:
        logger.error(f"FFmpeg exited with code {exit_code} at startup")
        proc = self.ffmpeg_process
        if proc and proc.stderr:
            try:
                stderr_output = proc.stderr.read() or b""
                if stderr_output:
                    text = stderr_output.decode("utf-8", "replace")[-2000:]
                    logger.error("FFmpeg error output: %s", self._masked_text(text))
            except Exception as e:
                logger.debug(f"Could not read FFmpeg stderr: {e}")

    def _retry_with_software_encoder(self, pump: FramePump) -> bool:
        """Hardware encode failed at startup — retry once with libx264.

        `self._last_cmd` / `self._last_webcam_url` were recorded by
        `_spawn_pipeline` right before Popen.
        """
        cmd = list(self._last_cmd or [])
        if not cmd or "-c:v" not in cmd:
            self._kill_ffmpeg()
            return False
        if cmd[cmd.index("-c:v") + 1] == "libx264":
            self._kill_ffmpeg()
            return False
        logger.warning("Hardware encoder failed; falling back to libx264")
        original_detect = self._detect_h264_encoder
        self._detect_h264_encoder = lambda: "libx264"
        try:
            pump.stop()
            self.frame_pump = None
            if not self._spawn_pipeline(self._last_webcam_url):
                self._kill_ffmpeg()
                return False
            return True
        finally:
            self._detect_h264_encoder = original_detect

    def _kill_ffmpeg(self) -> None:
        if self.audio_server is not None:
            if self.on_kill_audio is not None:
                # Hand the live server back to SpoolUp's standby slot so
                # music survives stream stop (24/7 radio-style behavior).
                try:
                    self.on_kill_audio(self.audio_server)
                except Exception as e:
                    logger.error("on_kill_audio failed, stopping server: %s", e)
                    self.audio_server.stop()
            else:
                self.audio_server.stop()
            self.audio_server = None
        if self.frame_pump is not None:
            self.frame_pump.stop()
            self.frame_pump = None
        if self.ffmpeg_process is not None:
            logger.info("Terminating existing FFmpeg process")
            self.ffmpeg_process.terminate()
            try:
                self.ffmpeg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ffmpeg_process.kill()
                self.ffmpeg_process.wait()
            self.ffmpeg_process = None

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
            logger.info(
                "Stream URL: %s/%s",
                ingestion_info["ingestionAddress"],
                self._mask_key(ingestion_info["streamName"]),
            )

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
            filename = print_stats.get("filename", "")
            filament = print_stats.get("filament_used", "N/A")
            current_layer = print_stats.get("current_layer", "N/A")
            total_layers = print_stats.get("total_layers", "N/A")
            estimate = print_stats.get("estimate", "N/A")
            slicer_time = print_stats.get("slicer_time", "N/A")
            total_time = print_stats.get("total_time", "N/A")
            eta = print_stats.get("eta", "N/A")
            speed = print_stats.get("speed", "N/A")
            flow_rate = print_stats.get("flow_rate", "N/A")
            
            # Temperatures with current and target
            extruder_temp_str = print_stats.get("extruder_temp_str", "N/A")
            extruder_target_str = print_stats.get("extruder_target_str", "N/A")
            bed_temp_str = print_stats.get("bed_temp_str", "N/A")
            bed_target_str = print_stats.get("bed_target_str", "N/A")
            chamber_temp_str = print_stats.get("chamber_temp_str", "N/A")
            mcu_temp_str = print_stats.get("mcu_temp_str", "N/A")

            # Calculate progress for progress bar
            progress_pct = 0.0
            # Use display_status.progress (0.0-1.0) if available
            if hasattr(self, '_display_progress') and self._display_progress > 0:
                progress_pct = self._display_progress * 100
            # Fallback to stats progress field
            elif "progress" in print_stats and print_stats["progress"] > 0:
                progress_pct = print_stats["progress"] * 100
            elif isinstance(total_layers, (int, float)) and total_layers > 0:
                progress_pct = (current_layer / total_layers) * 100 if isinstance(current_layer, (int, float)) else 0.0
            
            # Build visual progress bar
            bar_width = 30
            filled = int((progress_pct / 100) * bar_width)
            progress_bar = "█" * filled + "░" * (bar_width - filled)
            
            # File name section
            if filename and filename != "Unknown":
                lines.extend([
                    f"📄 File: {filename}",
                    "",
                ])
            
            # Temperatures section - table-like format
            lines.extend([
                "🌡️ Temperatures",
                "━" * 40,
                f"{'Name':<18} {'Current':<12} {'Target':<12}",
                f"{'─'*18} {'─'*12} {'─'*12}",
                f"{'Extruder':<18} {extruder_temp_str:<12} {extruder_target_str:<12}",
                f"{'Heater Bed':<18} {bed_temp_str:<12} {bed_target_str:<12}",
            ])
            
            if chamber_temp_str != "N/A":
                lines.append(f"{'Chamber Temp':<18} {chamber_temp_str:<12} {'─'*12}")
            
            if mcu_temp_str != "N/A":
                lines.append(f"{'Mcu Temp':<18} {mcu_temp_str:<12} {'─'*12}")
            
            lines.append("")
            
            # Print statistics section
            lines.extend([
                "📊 Print Statistics",
                "━" * 40,
                f"{'Speed:':<18} {speed}",
                f"{'Flow:':<18} {flow_rate}",
                f"{'Filament:':<18} {filament}",
                f"{'Layer:':<18} {current_layer} of {total_layers}",
                "",
                f"{'Progress:':<18} {progress_pct:.1f}%",
                f"[{progress_bar}]",
                f"{'Estimate:':<18} {estimate}",
                f"{'Slicer:':<18} {slicer_time}",
                f"{'Total:':<18} {total_time}",
                f"{'ETA:':<18} {eta}",
            ])
        else:
            lines.append("Statistics will be updated as the print progresses...")

        # Use stream start time if available, otherwise current time
        start_time_str = "Unknown"
        if self.live_broadcast and self.live_broadcast.get("snippet", {}).get("scheduledStartTime"):
            start_time_str = self.live_broadcast["snippet"]["scheduledStartTime"]
        else:
            start_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

        lines.extend(
            [
                "",
                "━" * 40,
                "🔴 Live from Klipper 3D Printer",
                f"⏱️  Started at: {start_time_str}",
            ]
        )

        return "\n".join(lines)

    def _wait_for_stream_active(self, stream_id: str, timeout: int = 30) -> bool:
        """Wait for the stream to become active (receiving data from FFmpeg)."""
        logger.info(f"Waiting for stream {stream_id} to become active...")
        start_time = time.time()
        last_status = None
        status_count = 0
        while time.time() - start_time < timeout:
            try:
                stream = (
                    self.youtube.liveStreams()
                    .list(part="status", id=stream_id)
                    .execute()
                )
                if stream.get("items"):
                    status = stream["items"][0]["status"]["streamStatus"]
                    health = stream["items"][0]["status"].get("healthStatus", {})
                    health_status = health.get("status", "unknown")

                    if status != last_status:
                        logger.info(
                            f"Stream status changed: {last_status} -> {status} (health: {health_status})"
                        )
                        last_status = status
                        status_count = 0
                    else:
                        status_count += 1
                        if status_count % 5 == 0:
                            logger.info(
                                f"Stream still {status} after {status_count * 2}s (health: {health_status})"
                            )

                    if status == "active":
                        logger.info("Stream is now active")
                        return True
                    elif status == "error":
                        logger.error("Stream is in error state")
                        self._log_ffmpeg_status()
                        return False
                    elif status == "inactive" and status_count >= 3:
                        self._log_ffmpeg_status()

            except Exception as e:
                logger.warning(f"Failed to check stream status: {e}")
            time.sleep(2)
        logger.warning(f"Stream did not become active within {timeout} seconds")
        self._log_ffmpeg_status()
        return False

    def _log_ffmpeg_status(self):
        if self.ffmpeg_process:
            exit_code = self.ffmpeg_process.poll()
            if exit_code is not None:
                logger.error(f"FFmpeg process has exited with code: {exit_code}")
            else:
                logger.info("FFmpeg process is still running")
        else:
            logger.warning("FFmpeg process not available")

    def _wait_for_stream_healthy(self, stream_id: str, timeout: int = 60) -> bool:
        """Wait for stream to be active with good health before going live."""
        logger.info(f"Waiting for stream {stream_id} to be healthy...")
        start_time = time.time()
        last_status = None
        last_health = None
        while time.time() - start_time < timeout:
            try:
                stream = (
                    self.youtube.liveStreams()
                    .list(part="status", id=stream_id)
                    .execute()
                )
                if stream.get("items"):
                    status = stream["items"][0]["status"]["streamStatus"]
                    health = stream["items"][0]["status"].get("healthStatus", {})
                    health_status = health.get("status", "unknown")

                    if status != last_status or health_status != last_health:
                        logger.info(
                            f"Stream health check: status={status}, health={health_status}"
                        )
                        last_status = status
                        last_health = health_status

                    if status == "active" and health_status == "good":
                        logger.info("Stream is active and healthy")
                        return True
                    elif status == "error":
                        logger.error("Stream is in error state")
                        return False

            except Exception as e:
                logger.warning(f"Stream health check failed: {e}")
            time.sleep(2)
        logger.warning(f"Stream did not become healthy within {timeout} seconds")
        return False

    def _test_rtmp_connectivity(self):
        import socket

        try:
            host = "a.rtmp.youtube.com"
            port = 1935
            logger.info(f"Testing TCP connection to {host}:{port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            if result == 0:
                logger.info(f"TCP connection to {host}:{port} successful")
            else:
                logger.error(
                    f"TCP connection to {host}:{port} failed with error code: {result}"
                )
            sock.close()
        except Exception as e:
            logger.error(f"RTMP connectivity test failed: {e}")

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

            if current_status == "testStarting" and status == "live":
                logger.info("Broadcast is still transitioning to testing, waiting...")
                time.sleep(5)
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

    def _check_stream_health(self) -> tuple[bool, str, dict]:
        """Check stream health - returns status but never marks as unhealthy for bad health.

        Even if health is 'bad' or 'readable', the stream continues. This mimics
        ffmpeg behavior which keeps running even when frames freeze.
        """
        try:
            if not self.live_stream:
                return True, "No live stream", {}
            logger.info(f"Checking stream health for {self.live_stream['id']}...")
            stream = (
                self.youtube.liveStreams()
                .list(part="status", id=self.live_stream["id"])
                .execute()
            )
            if not stream.get("items"):
                logger.warning("Stream not found in health check")
                return True, "Stream not found", {}
            status = stream["items"][0]["status"]
            stream_status = status.get("streamStatus")
            health_status = status.get("healthStatus", {})
            health = health_status.get("status")
            reasons = health_status.get("configurationIssues", [])

            logger.info(f"Stream status: {stream_status}, Health: {health}")
            if reasons:
                for reason in reasons:
                    logger.warning(f"Health issue: {reason}")

            # Only treat stream errors as unhealthy - bad health is acceptable
            if stream_status == "error":
                logger.error("Stream is in error state")
                return (
                    False,
                    f"Stream error state",
                    {"status": stream_status, "health": health, "reasons": reasons},
                )

            # Treat inactive as a warning but not unhealthy - ffmpeg may recover
            if stream_status == "inactive":
                logger.warning("Stream is inactive, but continuing...")
                return (
                    True,
                    f"Status: {stream_status}, Health: {health}",
                    {"status": stream_status, "health": health, "reasons": reasons},
                )

            # Even 'bad' health is acceptable - keep streaming like ffmpeg does
            if health == "bad":
                logger.warning(f"Health is {health}, but continuing to stream...")
                return (
                    True,
                    f"Status: {stream_status}, Health: {health}",
                    {"status": stream_status, "health": health, "reasons": reasons},
                )

            return (
                True,
                f"Status: {stream_status}, Health: {health}",
                {"status": stream_status, "health": health, "reasons": reasons},
            )
        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            # Even on health check errors, keep streaming
            return True, f"Health check error (continuing): {e}", {}

    def _health_check_loop(self):
        consecutive_issues = 0
        stream_start_time = time.time()
        check_count = 0

        logger.info(
            "Health check loop started - will continue streaming regardless of health status"
        )
        while self.is_streaming:
            time.sleep(30)
            if not self.is_streaming:
                logger.info("Health check loop exiting - is_streaming is False")
                break

            check_count += 1
            elapsed = time.time() - stream_start_time
            logger.info(f"Health check #{check_count} after {elapsed:.0f}s")

            is_healthy, message, details = self._check_stream_health()
            health = details.get("health", "unknown")
            reasons = details.get("reasons", [])
            stream_status = details.get("status", "unknown")

            if is_healthy and stream_status == "active" and health == "good":
                consecutive_issues = 0
                logger.info(f"Health check: {message}")
            else:
                logger.warning(f"Health check issue (continuing anyway): {message}")

            # Log latency/buffer indicators
            latency_indicators = [
                "videoIngestionStarved",
                "videoIngestionFasterThanRealtime",
                "videoProcessingStalled",
            ]
            for reason in reasons:
                reason_type = reason.get("type", "")
                if reason_type in latency_indicators:
                    logger.warning(f"Latency indicator detected: {reason_type}")
                if "buffer" in reason.get("description", "").lower():
                    logger.warning(
                        f"Buffer issue detected: {reason.get('description')}"
                    )

            is_starvation = any(
                r.get("type") == "videoIngestionStarved" for r in reasons
            )
            is_inactive = stream_status == "inactive"
            is_bad_health = health == "bad"

            if is_starvation or is_inactive or is_bad_health:
                consecutive_issues += 1
                logger.warning(
                    f"Stream issue detected: starvation={is_starvation}, inactive={is_inactive}, bad_health={is_bad_health} ({consecutive_issues} consecutive checks)"
                )

                if consecutive_issues >= 5:
                    logger.error(
                        "Stream unhealthy for 150 seconds - attempting FFmpeg restart"
                    )
                    self._restart_ffmpeg_stream()
                    consecutive_issues = 0
                    stream_start_time = time.time()
            else:
                consecutive_issues = 0

        logger.info("Health check loop ended")

    def _restart_ffmpeg_stream(self) -> bool:
        """Kill and respawn the ffmpeg pipeline in place.

        On success restores streaming state (is_streaming=True) and restarts
        the ffmpeg/health monitor threads (the old monitor thread already
        exited — it cleared is_streaming when it detected the death).

        Returns True when the pipeline was respawned and state restored,
        False otherwise.
        """
        logger.warning("Restarting FFmpeg stream due to ingestion starvation")
        self._stopping = True
        try:
            try:
                self._kill_ffmpeg()
            except Exception as e:
                logger.error(f"Failed to stop old pipeline: {e}")
            time.sleep(3)
            try:
                # Reload config to pick up any changes
                self.config.load()

                webcam_url = (
                    self.config.get("webcam_url") or "http://localhost:8080/?action=stream"
                )
                logger.info("Restarting FFmpeg with fresh connection")

                if not self.stream_url:
                    logger.error("Cannot restart - no stream URL available")
                    return False

                if not self._spawn_pipeline(webcam_url):
                    logger.error("FFmpeg restart failed")
                    return False
                logger.info("FFmpeg pipeline restarted successfully")
                self.is_streaming = True
                self._start_ffmpeg_monitor()
                if self.live_stream:
                    self._start_health_monitor()
                return True
            except Exception as e:
                logger.error(f"Failed to restart FFmpeg stream: {e}")
                return False
        finally:
            self._stopping = False

    def _start_health_monitor(self):
        if self._health_check_thread is not None and self._health_check_thread.is_alive():
            return
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
            logger.info("Testing RTMP connectivity to YouTube...")
            self._test_rtmp_connectivity()

            if not self._spawn_pipeline(webcam_url):
                logger.error(
                    "Pipeline failed to start (no frames from %s or FFmpeg died)",
                    webcam_url,
                )
                return False

            if self.live_stream and self.live_broadcast:
                stream_id = self.live_stream["id"]
                broadcast_id = self.live_broadcast["id"]

                if not self._wait_for_stream_active(stream_id, timeout=60):
                    if self.ffmpeg_process.poll() is not None:
                        logger.error(
                            "FFmpeg process died while waiting for stream to become active"
                        )
                        return False
                    logger.warning(
                        "Stream did not become active within 60s, continuing anyway"
                    )
                    logger.info(
                        "Stream may still become active - health check will monitor"
                    )

                if self.ffmpeg_process.poll() is not None:
                    logger.error("FFmpeg process died before state transition")
                    return False

                if not self._transition_broadcast(broadcast_id, "testing"):
                    logger.error("Failed to transition to testing state")
                    return False

                # Wait for stream to be healthy before going live
                # YouTube requires good health to actually show the broadcast
                if not self._wait_for_stream_healthy(stream_id, timeout=45):
                    logger.warning(
                        "Stream not healthy before live transition, attempting anyway"
                    )

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
                        stderr_output = self.ffmpeg_process.stderr.read() or b""
                        if stderr_output:
                            text = stderr_output.decode("utf-8", "replace")[
                                -1000:
                            ]  # Last 1000 chars
                            logger.error(f"FFmpeg stderr: {self._masked_text(text)}")
                    except:
                        pass
                if not self._stopping:
                    self._ffmpeg_died_unexpectedly = True
                    if self.on_ffmpeg_death is not None:
                        try:
                            self.on_ffmpeg_death()
                        except Exception as e:
                            logger.error(f"on_ffmpeg_death callback failed: {e}")
                self.is_streaming = False
                break
        logger.info("FFmpeg monitor stopped")

    def _start_ffmpeg_monitor(self):
        if self._ffmpeg_monitor_thread is not None and self._ffmpeg_monitor_thread.is_alive():
            return
        self._ffmpeg_monitor_thread = threading.Thread(target=self._ffmpeg_monitor_loop)
        self._ffmpeg_monitor_thread.daemon = True
        self._ffmpeg_monitor_thread.start()

    def _start_ffmpeg_stderr_logger(self):
        def log_stderr():
            proc = self.ffmpeg_process
            if not proc or not proc.stderr:
                return
            try:
                for line in iter(proc.stderr.readline, b""):
                    if not line:
                        break
                    text = line.decode("utf-8", "replace").strip()
                    if text:
                        m = re.search(r"speed=\s*([0-9.]+)x", text)
                        if m:
                            try:
                                self.encode_speed = float(m.group(1))
                            except ValueError:
                                pass
                        logger.info(f"FFmpeg: {self._masked_text(text)}")
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
        self._stopping = True
        try:
            if self.live_broadcast:
                delay = 15
                logger.info(f"Waiting {delay}s before ending broadcast...")
                time.sleep(delay)
                self._transition_broadcast(self.live_broadcast["id"], "complete")

            self._kill_ffmpeg()

            self.is_streaming = False
            logger.info("Live streaming stopped")

        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
        finally:
            self._stopping = False

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
        self.dashboard_thread = None
        self.dashboard_ctx = None
        self._action_thread = None
        self.standby_audio = None
        self.audio_library = None
        self.playlist_state = None
        self.session_store = None
        self._active_session_id = None
        self.watchdog = None
        self.updater: Optional["Updater"] = None
        self._update_checker_thread = None
        self._pending_restart = False
        self._update_runner_lock = threading.Lock()
        self._update_running = False
        self._stop = False

    def _is_streaming_now(self) -> bool:
        return bool(self.streamer is not None and self.streamer.is_streaming)

    @staticmethod
    def failed_steps_check(applied: Dict[str, Any]):
        steps = applied.get("steps") or []
        for step in steps if False else steps:
            if step.get("rc") not in (0, None):
                return step
        return None

    def _banner(self, msg: str) -> None:
        ctx = getattr(self, "dashboard_ctx", None)
        if ctx is not None:
            ctx.add_banner(msg)
        logger.warning(msg)

    def _start_update_checker(self) -> None:
        data_dir = self.config.get("data_dir") or "data"
        from spoolup.updater import Updater

        self.updater = Updater(
            repo_root=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            state_path=os.path.join(data_dir, "update_state.json"),
        )
        if self.updater.get_state().get("pending_restart"):
            self._pending_restart = True
        if self.dashboard_ctx is not None:
            self.dashboard_ctx.updater = self.updater
            self.dashboard_ctx.get_update_status = self._get_update_status
        if not self.config.get("auto_update_enabled", True):
            logger.info("Auto-update checker disabled; manual updates still available")
            return

        def checker():
            time.sleep(60)  # boot grace
            while True:
                try:
                    self._auto_update_once()
                except Exception as e:
                    logger.error("auto-update sweep failed: %s", e)
                hours = float(self.config.get("auto_update_interval_h", 2) or 2)
                time.sleep(max(0.25, hours) * 3600)

        self._update_checker_thread = threading.Thread(
            target=checker, daemon=True, name="spoolup-updates"
        )
        self._update_checker_thread.start()
        logger.info("Auto-update checker started (interval=%sh)",
                    self.config.get("auto_update_interval_h", 2))

    def _get_update_status(self) -> Dict[str, Any]:
        state = self.updater.get_state() if self.updater is not None else {}
        return {
            "pending_restart": self._pending_restart,
            "last_check": state.get("last_check"),
            "last_apply": state.get("last_apply"),
            "auto_update_enabled": bool(self.config.get("auto_update_enabled", True)),
        }

    def _auto_update_once(self) -> None:
        if self.updater is None or self._update_running:
            return
        with self._update_runner_lock:
            if self._update_running:
                return
            self._update_running = True
        try:
            check = self.updater.check()
            self.updater.set_state(last_check=check)
            if not check.get("ok") or not check.get("ahead_by"):
                return
            logger.info("Auto-update: %d new commit(s) available", check["ahead_by"])
            applied = self.updater.apply()
            self.updater.set_state(last_apply=applied)
            if not applied.get("ok"):
                tail = ""
                failed_steps = [s for s in applied.get("steps", []) if s.get("rc") != 0]
                if failed_steps_check(applied):
                    tail = failed_steps_check(applied).get("tail", "")[-160:]
                    self._banner("update failed: %s — %s"
                                 % (applied.get("error"), tail))
                else:
                    self._banner("update failed: %s" % applied.get("error"))
                return
            self._stage_restart_if_needed(applied)
        finally:
            self._update_running = False

    def _stage_restart_if_needed(self, applied: Dict[str, Any]) -> None:
        if not applied.get("changed") and not self._pending_restart:
            return
        if self._is_streaming_now():
            self._pending_restart = True
            self.updater.set_state(pending_restart=True)
            self._banner("update staged — will restart when the stream ends")
            logger.info("Update staged; restart deferred until stream end")
        else:
            self.restart_app()

    def _maybe_restart_pending(self) -> None:
        if not self._pending_restart:
            return
        if self._is_streaming_now():
            return
        logger.info("Stream ended — executing deferred update restart")
        self.restart_app()

    def restart_app(self) -> None:
        logger.warning("Restarting application to apply update...")
        if self.updater is not None:
            self.updater.set_state(pending_restart=False)
        self._pending_restart = False
        argv = [sys.executable, "-m", "spoolup", "-c",
                self.config.config_file]
        logger.info("exec: %s", " ".join(argv))
        try:
            if self.streamer is not None and self.streamer.is_streaming:
                self.streamer.stop_streaming()
        except Exception as e:
            logger.error("stop before restart failed: %s", e)
        os.execv(sys.executable, argv)

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
                self.streamer = StreamManager(self.config, self.youtube)
                self.streamer.audio_server_provider = self._adopt_standby_audio
                self.streamer.on_kill_audio = self._reclaim_audio_server
                if self.watchdog is not None:
                    self.streamer.on_ffmpeg_death = lambda: self.watchdog.add_banner(
                        "watchdog: ffmpeg died unexpectedly — restart pending"
                    )
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
        self._record_session_start(filename)

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
        session_id = self._active_session_id

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
                    self._record_session_upload(session_id, True, video_url)
                else:
                    self._record_session_upload(session_id, False, "upload failed")
            else:
                logger.error(f"Timelapse file not found for: {filename}")
                logger.error(f"Check timelapse_dir config: {self.config.get('timelapse_dir')}")
                self._record_session_upload(session_id, False, "timelapse not found")

        self._record_session_end("complete")
        self._maybe_restart_pending()

    def on_print_cancelled(self, filename: str):
        logger.info("Print cancelled")

        if self.config.get("enable_live_stream", True) and self.streamer:
            if self.streamer.is_streaming:
                self.streamer.stop_streaming()

        self._record_session_end("cancelled")
        self._maybe_restart_pending()

    def _platforms(self) -> List[str]:
        platforms = ["youtube"]
        if self.config.get("kick_enabled"):
            platforms.append("kick")
        return platforms

    def _record_session_start(self, filename: str) -> None:
        if self.session_store is None:
            return
        try:
            self._active_session_id = self.session_store.record_start(
                filename,
                datetime.now(timezone.utc).isoformat(),
                self._platforms(),
            )
        except Exception as e:
            logger.error("session record_start failed: %s", e)

    def _record_session_end(self, outcome: str) -> None:
        if self.session_store is None or self._active_session_id is None:
            return
        try:
            self.session_store.record_end(self._active_session_id, outcome)
        except Exception as e:
            logger.error("session record_end failed: %s", e)
        self._active_session_id = None

    def _record_session_upload(
        self, session_id: Optional[int], ok: bool, detail: str
    ) -> None:
        if self.session_store is None or session_id is None:
            return
        try:
            self.session_store.record_upload(session_id, ok, detail)
        except Exception as e:
            logger.error("session record_upload failed: %s", e)

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
        logger.info(f"Searching for timelapse: {base_name}.* in {timelapse_dir}")

        for ext in [".mp4", ".mkv", ".avi"]:
            timelapse_path = os.path.join(timelapse_dir, f"{base_name}{ext}")
            if os.path.exists(timelapse_path):
                logger.info(f"Found exact match: {timelapse_path}")
                return timelapse_path

            for f in os.listdir(timelapse_dir):
                if f.startswith(base_name) and f.endswith(ext):
                    match_path = os.path.join(timelapse_dir, f)
                    logger.info(f"Found prefix match: {match_path}")
                    return match_path

        files = [
            os.path.join(timelapse_dir, f)
            for f in os.listdir(timelapse_dir)
            if f.endswith((".mp4", ".mkv", ".avi"))
        ]

        if files:
            most_recent = max(files, key=os.path.getmtime)
            age_hours = (time.time() - os.path.getmtime(most_recent)) / 3600
            logger.info(f"Fallback to most recent: {most_recent} (age: {age_hours:.1f}h)")
            if time.time() - os.path.getmtime(most_recent) < 86400:
                return most_recent
            logger.warning(f"Most recent timelapse is too old ({age_hours:.1f}h)")

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
            moonraker_port = self.config.get("moonraker_port") or "4409"
            list_url = f"http://{printer_ip}:{moonraker_port}/server/files/list?root=timelapse"
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

    def _start_dashboard(self) -> None:
        # Audio init must run even when the dashboard is disabled: the
        # action worker handlers and the standby server depend on it.
        try:
            from spoolup.audio_library import AudioLibrary, PlaylistState
            from spoolup.audio_server import AudioServer

            data_dir = self.config.get("data_dir") or "data"
            self.audio_library = AudioLibrary(data_dir)
            self.playlist_state = PlaylistState(
                os.path.join(data_dir, "audio_playlist.json")
            )
            if self.config.get("audio_server_enabled", True):
                state = self.playlist_state.load()
                volume = state.get("volume")
                if volume is None:
                    volume = float(
                        self.config.get("audio_default_volume", 0.8) or 0.8
                    )
                self.standby_audio = AudioServer(volume=float(volume))
        except Exception as e:
            logger.error("Audio init failed (music disabled): %s", e)
        try:
            from spoolup.sessions import SessionStore

            data_dir = self.config.get("data_dir") or "data"
            self.session_store = SessionStore(
                os.path.join(data_dir, "sessions.json")
            )
        except Exception as e:
            logger.error("session store init failed: %s", e)
        self._restore_audio_from_state()
        if not self.config.get("dashboard_enabled", True):
            return
        try:
            from spoolup.dashboard.app import create_app
            import uvicorn

            self.dashboard_ctx = build_dashboard_context(self)
            self.dashboard_ctx.audio_library = self.audio_library
            self.dashboard_ctx.playlist_state = self.playlist_state
            self.dashboard_ctx.get_audio_server = self._current_audio_server
            self.dashboard_ctx.sessions = self.session_store
            self.dashboard_ctx.updater = self.updater
            self.dashboard_ctx.get_update_status = self._get_update_status
            handler = self.dashboard_ctx.log_handler
            handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
            logging.getLogger().addHandler(handler)

            config = uvicorn.Config(
                create_app(self.dashboard_ctx),
                host=self.config.get("dashboard_host") or "127.0.0.1",
                port=int(self.config.get("dashboard_port") or 8007),
                log_level="warning",
            )
            server = uvicorn.Server(config)
            self.dashboard_thread = threading.Thread(
                target=server.run, daemon=True, name="spoolup-dashboard"
            )
            self.dashboard_thread.start()
            logger.info(
                "Dashboard available at http://%s:%d",
                self.config.get("dashboard_host") or "127.0.0.1",
                int(self.config.get("dashboard_port") or 8007),
            )
        except Exception as e:
            logger.error("Dashboard failed to start (streaming continues): %s", e)

    def _start_action_worker(self) -> None:
        self._action_thread = threading.Thread(
            target=self._action_worker_loop, daemon=True, name="spoolup-actions"
        )
        self._action_thread.start()

    def _action_worker_loop(self) -> None:
        ctx = self.dashboard_ctx
        while True:
            time.sleep(1.0)
            if ctx is None:
                continue
            for req in ctx.drain_actions():
                try:
                    self._handle_dashboard_action(req)
                except Exception as e:
                    logger.error("Dashboard action %s failed: %s", req.kind, e)

    def _handle_dashboard_action(self, req) -> None:
        s = self.streamer
        if req.kind == "audio_volume":
            srv = self._current_audio_server()
            if srv is not None:
                v = float(req.payload.get("volume", 0.8))
                srv.set_volume(v)
                if self.playlist_state is not None:
                    self.playlist_state.save({"volume": v})
            return
        if req.kind == "audio_source":
            self._apply_audio_source(req.payload)
            return
        if req.kind == "stream_stop":
            if s is not None and s.is_streaming:
                s.stop_streaming()
                logger.info("Dashboard: stream stopped")
            self._maybe_restart_pending()
            return
        if req.kind == "stream_restart":
            if s is not None and s.is_streaming:
                if s._restart_ffmpeg_stream():
                    logger.info("Dashboard: stream pipeline restarted")
                else:
                    logger.error("Dashboard: restart failed")
            else:
                logger.info("Dashboard: no live stream to restart")
            return
        if req.kind == "stream_start":
            if s is None:
                logger.warning("Dashboard: no streamer (enable_live_stream?)")
                return
            if s.is_streaming:
                logger.info("Dashboard: stream already running")
                return
            stats = self.moonraker.get_print_stats() if self.moonraker else {}
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            if s.create_live_stream(f"manual_{ts}.gcode", stats):
                webcam_url = self.config.get("webcam_url")
                if webcam_url and s.start_streaming(webcam_url):
                    logger.info("Dashboard: manual stream at %s", s.get_watch_url())
            else:
                logger.error("Dashboard: manual stream creation failed")
            return
        if req.kind == "update_apply":
            self._auto_update_once()
            return
        logger.warning("Dashboard: unsupported action kind %r", getattr(req, "kind", None))

    # ------- audio bridge (dashboard music control) -------
    def _current_audio_server(self):
        if self.streamer is not None and self.streamer.audio_server is not None:
            return self.streamer.audio_server
        return self.standby_audio

    def _adopt_standby_audio(self):
        """StreamManager provider: steal the standby server for streaming."""
        srv = self.standby_audio
        self.standby_audio = None
        return srv

    def _reclaim_audio_server(self, srv) -> None:
        """StreamManager on_kill hook: return the server to standby."""
        if self.standby_audio is None:
            self.standby_audio = srv
        else:
            srv.stop()

    def _apply_audio_source(self, payload: Dict[str, Any]) -> None:
        from spoolup.audio_server import (
            SilenceSource, FileSource, PlaylistSource,
        )
        srv = self._current_audio_server()
        if srv is None:
            logger.warning("audio_source ignored: no audio server")
            return
        kind = payload.get("source", "silence")
        if kind == "silence":
            srv.set_source(SilenceSource())
            if self.playlist_state is not None:
                self.playlist_state.save({"source": "silence", "track": None})
            return
        if kind == "library":
            if self.audio_library is None or self.playlist_state is None:
                logger.warning("audio_source library ignored: no library")
                return
            state = self.playlist_state.load()
            track_id = payload.get("track_id") or state.get("track")
            if track_id:
                path = self.audio_library.track_path(track_id)
                if path:
                    src = FileSource(path)
                    if src.exhausted():
                        logger.error(
                            "Audio decode failed for track %s "
                            "(ffmpeg/file broken)", track_id
                        )
                        src.close()
                        if self.dashboard_ctx is not None:
                            self.dashboard_ctx.add_banner(
                                "Audio decode failed for the selected track "
                                "— check ffmpeg and the file."
                            )
                        return
                    srv.set_source(src)
                    self.playlist_state.save({"source": "library", "track": track_id})
                    return
            paths = [self.audio_library.track_path(t) for t in state.get("order", [])]
            paths = [p for p in paths if p]
            if paths:
                srv.set_source(PlaylistSource(paths, loop=state.get("loop", True)))
                self.playlist_state.save({"source": "library"})
            else:
                srv.set_source(SilenceSource())
            return
        if kind == "spotify":
            self._apply_spotify_source(srv, payload)
            return
        logger.warning("audio_source: unknown kind %r", kind)

    def _apply_spotify_source(self, srv, payload: Dict[str, Any]) -> None:
        from spoolup.audio_server import LibrespotSource

        path = self.config.get("librespot_path") or ""
        user = self.config.get("spotify_username") or ""
        password = self.config.get("spotify_password") or ""
        if not path:
            logger.error("Spotify source requested but librespot_path is empty")
            if self.dashboard_ctx is not None:
                self.dashboard_ctx.add_banner(
                    "Spotify not configured — set librespot_path in Settings"
                )
            return
        data_dir = self.config.get("data_dir") or "data"
        cache_dir = os.path.join(data_dir, "spotify-cache")
        os.makedirs(cache_dir, exist_ok=True)
        src = LibrespotSource(
            path,
            username=user, password=password,
            cache_dir=cache_dir,
        )
        if src.exhausted():
            logger.error("librespot failed to start (kept the current source)")
            if self.dashboard_ctx is not None:
                self.dashboard_ctx.add_banner(
                    "librespot failed to start — check librespot_path"
                )
            src.close()
            return
        srv.set_source(src)
        if self.playlist_state is not None:
            self.playlist_state.save({"source": "spotify"})
        if self.dashboard_ctx is not None:
            self.dashboard_ctx.add_banner(
                "Spotify source active — select 'SpoolUp' as the playback "
                "device in your Spotify app"
            )

    def _restore_audio_from_state(self) -> None:
        """Restore the user's last music choice onto the standby server."""
        if self.playlist_state is None or self.standby_audio is None:
            return
        state = self.playlist_state.load()
        if state.get("source", "silence") == "silence":
            return
        self._apply_audio_source({
            "source": state["source"],
            "track_id": state.get("track"),
        })

    def _on_print_error_state(self) -> None:
        if not self.config.get("keep_stream_on_error", True):
            logger.warning("keep_stream_on_error=false — stopping stream on error state")
            if self.streamer is not None and self.streamer.is_streaming:
                self.streamer.stop_streaming()

    def _register_watchdog_checks(self) -> None:
        if self.watchdog is None:
            return

        def check_ffmpeg():
            s = self.streamer
            if s is None:
                return None
            # Flag-gated (set by _ffmpeg_monitor_loop on unexpected death);
            # the monitor clears is_streaming first, so is_streaming cannot
            # gate this check.
            if getattr(s, "_ffmpeg_died_unexpectedly", False):
                def heal_ffmpeg():
                    s._ffmpeg_died_unexpectedly = False
                    s._restart_ffmpeg_stream()
                return (
                    False,
                    "ffmpeg died while streaming — restarting pipeline",
                    heal_ffmpeg,
                )
            return None

        def check_pump_freshness():
            s = self.streamer
            if s is None or not getattr(s, "is_streaming", False):
                return None
            pump = getattr(s, "frame_pump", None)
            if pump is None:
                return None
            stats = getattr(pump, "last_stats", None)
            if stats is None:
                return None
            if time.time() - stats.get("ts", 0.0) > 60:
                return (
                    False,
                    "webcam frame pump stalled > 60s — restarting pipeline",
                    lambda: s._restart_ffmpeg_stream(),
                )
            return None

        def check_audio():
            if not self.config.get("audio_server_enabled", True):
                return None
            if not self._is_streaming_now():
                return None
            srv = self._current_audio_server()
            if srv is None:
                return None
            if srv is None:
                return None
            snap = srv.snapshot()
            if not snap.get("listening"):
                def heal_audio():
                    if srv._thread is None or not srv._thread.is_alive():
                        srv._stop.clear()
                        srv.start()
                return (False, "audio server not listening — restarting", heal_audio)
            return None

        def check_moonraker():
            if self.moonraker is None:
                return None
            state = getattr(self.moonraker, "print_state", "unknown")
            if state == "unknown" and not getattr(self.moonraker, "_initial_state_handled", True):
                return None
            ws = getattr(self.moonraker, "ws", None)
            if ws is None:
                return (
                    False,
                    "moonraker websocket disconnected — reconnect loop active",
                    None,
                )
            return None

        self.watchdog.register_check("ffmpeg", check_ffmpeg)
        self.watchdog.register_check("frame_pump", check_pump_freshness)
        self.watchdog.register_check("audio", check_audio)
        self.watchdog.register_check("moonraker", check_moonraker)

    def run(self):
        logger.info("=" * 60)
        logger.info("SpoolUp starting...")
        logger.info("=" * 60)

        # Dashboard must come up before credentials: in the true first-run
        # case (no config file yet) the setup wizard is the only way in.
        self._start_dashboard()
        self._start_action_worker()

        log_path = self.config.get("log_file") or ""
        if log_path:
            try:
                from logging.handlers import RotatingFileHandler

                parent = os.path.dirname(os.path.abspath(log_path))
                os.makedirs(parent, exist_ok=True)
                handler = RotatingFileHandler(
                    log_path, maxBytes=5 * 1024 * 1024, backupCount=3,
                )
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
                logging.getLogger().addHandler(handler)
                logger.info("File logging: %s", log_path)
            except Exception as e:
                logger.error("rotating log handler failed: %s", e)

        try:
            from spoolup.watchdog import Watchdog

            self.watchdog = Watchdog(
                interval=int(self.config.get("watchdog_interval", 30) or 30)
            )
            if self.dashboard_ctx is not None:
                self.watchdog.banners = self.dashboard_ctx.banners  # shared list
            self._register_watchdog_checks()
            self.watchdog.start()
            if self.streamer is not None and self.watchdog is not None:
                self.streamer.on_ffmpeg_death = lambda: self.watchdog.add_banner(
                    "watchdog: ffmpeg died unexpectedly — restart pending"
                )
        except Exception as e:
            logger.error("watchdog init failed: %s", e)

        if not self.load_youtube_credentials():
            if os.path.exists(self.config.config_file):
                logger.error("YouTube credentials not available. Exiting.")
                logger.error("Please authenticate using spoolup-auth on your PC/Mac")
                return 1
            logger.warning(
                "First-run: waiting for configuration via dashboard wizard"
            )

        moonraker_url: str = self.config.get("moonraker_url") or "http://localhost:7125"
        self.moonraker = MoonrakerClient(moonraker_url)
        self.moonraker.on_error_state = self._on_print_error_state

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

        first_run = not os.path.exists(self.config.config_file)
        if not self.moonraker.connect_websocket():
            if not first_run:
                logger.error("Failed to connect to Moonraker. Exiting.")
                return 1
            logger.warning(
                f"First-run: could not connect to Moonraker at {moonraker_url}. "
                "Continuing so the dashboard wizard can fix moonraker_url; "
                "the reconnection loop will keep retrying in the background."
            )
        else:
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

        # Use WebSocket state if available (more reliable for real-time state)
        effective_state = current_state
        if self.moonraker.print_state != "unknown":
            effective_state = self.moonraker.print_state
            if current_state != effective_state:
                logger.info(f"Using WebSocket state ({effective_state}) instead of HTTP ({current_state})")

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
        elif effective_state and effective_state not in ["unknown", "standby"]:
            # Only update state from HTTP if WebSocket hasn't provided state yet
            if self.moonraker.print_state == "unknown":
                logger.info(f"Print not active, current state: {effective_state}")
                self.moonraker.print_state = effective_state

        reconnect_thread = self.moonraker.start_reconnection_loop()

        self._start_update_checker()

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
