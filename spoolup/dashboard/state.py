"""Framework-free bridge between the SpoolUp runtime and the web dashboard.

The dashboard NEVER mutates streaming state directly: state.py builds
read-only snapshots and posts serial action requests for the runtime to
consume. No FastAPI imports here — synchronization lives in one class.
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MASKED = "***"


class DashboardRequest:
    __slots__ = ("kind", "payload")

    def __init__(self, kind: str, payload: Optional[Dict[str, Any]] = None):
        self.kind = kind
        self.payload = payload or {}

    def __repr__(self) -> str:
        return "DashboardRequest(kind=%s)" % self.kind


class RecentLogHandler(logging.Handler):
    """Ring buffer of formatted log lines for the /logs page."""

    def __init__(self, limit: int = 200):
        super().__init__()
        self._buffer: deque = deque(maxlen=limit)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.append(self.format(record))
        except Exception:
            pass

    def tail(self, limit: int = 200) -> List[str]:
        return list(self._buffer)[-limit:]


class RuntimeContext:
    """Everything the dashboard is allowed to see and request.

    Construction values (all callables injected by main.py):
      config_get(key, default) -> value
      config_keys() -> List[str]
      secret_keys() -> List[str]
      config_file -> path
      save_config(values) -> bool
      test_webcam(url) -> bool
      test_moonraker(url) -> bool
    """

    def __init__(
        self,
        runtime: Any,
        config_get: Callable[[str, Any], Any],
        config_keys: Callable[[], List[str]],
        secret_keys: Callable[[], List[str]],
        config_file: str,
        save_config: Callable[[Dict[str, Any]], bool],
        test_webcam: Callable[[str], bool],
        test_moonraker: Callable[[str], bool],
    ):
        self.runtime = runtime
        self._config_get = config_get
        # Accept either callables or plain lists for the key providers.
        self._config_keys = (
            config_keys if callable(config_keys) else (lambda: list(config_keys))
        )
        self._secret_keys = (
            secret_keys if callable(secret_keys) else (lambda: list(secret_keys))
        )
        self.config_file = config_file
        self.save_config = save_config
        self.test_webcam = test_webcam
        self.test_moonraker = test_moonraker
        self.log_handler = RecentLogHandler(limit=200)
        self.banners: List[str] = []
        self._start_time = time.time()
        self._lock = threading.Lock()
        self._pending: List[DashboardRequest] = []
        # Audio bridge — injected by main.py after construction.
        self.audio_library = None
        self.playlist_state = None
        self.get_audio_server = lambda: None
        # Session history — injected by main.py after construction.
        self.sessions = None
        # Auto-update bridge — injected by main.py after construction.
        self.updater = None
        self.get_update_status = None

    # ------- config ------
    def config_values(self) -> Dict[str, Any]:
        return {k: self._config_get(k, None) for k in self._config_keys()}

    def secret_keys(self) -> List[str]:
        return self._secret_keys()

    def mask_config(self, values: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(values)
        for key in self._secret_keys():
            if out.get(key):
                out[key] = MASKED
        return out

    # ------- snapshots -------
    def _pump_snapshot(self, pump: Any) -> Dict[str, Any]:
        return {
            "fps": getattr(pump, "fps", None),
            "buffer": pump.buffer_size() if hasattr(pump, "buffer_size") else None,
            "dup_rate": getattr(pump, "last_dup_rate", None),
            "read_rate": getattr(pump, "last_read_rate", None),
        }

    def status(self) -> Dict[str, Any]:
        rt = self.runtime
        streamer = getattr(rt, "streamer", None)
        moonraker = getattr(rt, "moonraker", None)
        print_card: Dict[str, Any] = {}
        try:
            if moonraker is not None:
                print_card = moonraker.get_print_stats()
        except Exception as e:
            logger.debug("print stats unavailable: %s", e)

        pump_doc = None
        youtube_up = False
        kick_up = False
        if streamer is not None:
            pump = getattr(streamer, "frame_pump", None)
            if pump is not None:
                pump_doc = self._pump_snapshot(pump)
            youtube_up = bool(streamer.is_streaming and pump_doc)
            kick_up = bool(
                self._config_get("kick_enabled", False) and streamer.is_streaming
            )

        audio_doc = None
        try:
            srv = self.get_audio_server()
            if srv is not None:
                audio_doc = srv.snapshot()
        except Exception as e:
            logger.debug("audio snapshot unavailable: %s", e)

        try:
            sessions_doc = (
                self.sessions.list_recent(10) if self.sessions is not None else []
            )
        except Exception as e:
            logger.debug("sessions snapshot unavailable: %s", e)
            sessions_doc = []

        doc = {
            "print": print_card,
            "stream": {
                "is_streaming": bool(
                    streamer is not None and streamer.is_streaming
                ),
                "watch_url": streamer.get_watch_url()
                if streamer is not None and getattr(streamer, "live_broadcast", None)
                else None,
                "sinks": {
                    "youtube": {
                        "up": youtube_up,
                        "health": getattr(streamer, "last_health", None)
                        if streamer is not None else None,
                        "watch_url": streamer.get_watch_url()
                        if streamer is not None and streamer.live_broadcast
                        else None,
                    },
                    "kick": {
                        "configured": bool(self._config_get("kick_enabled")),
                        "up": kick_up,
                        "channel": self._config_get("kick_channel_url") or "",
                    },
                },
                "pump": pump_doc,
                "encode_speed": getattr(streamer, "encode_speed", None)
                if streamer is not None else None,
            },
            "uptime_seconds": int(time.time() - self._start_time),
            "banners": list(self.banners),
        }
        doc["audio"] = {
            "enabled": bool(self._config_get("audio_server_enabled", True)),
            "snapshot": audio_doc,
        }
        doc["sessions"] = sessions_doc
        doc["update"] = (
            self.get_update_status()
            if getattr(self, "get_update_status", None)
            else None
        )
        return doc

    # ------- logs -------
    def add_banner(self, message: str) -> None:
        if message in self.banners:
            return
        self.banners.append(message)
        del self.banners[: max(0, len(self.banners) - 20)]

    def logs(self, limit: int = 200) -> List[str]:
        return self.log_handler.tail(limit)

    # ------- serial actions -------
    def submit(self, req: DashboardRequest) -> bool:
        with self._lock:
            if self._pending:
                return False
            self._pending = [req]
            return True

    def drain_actions(self) -> List[DashboardRequest]:
        with self._lock:
            if not self._pending:
                return []
            out = self._pending
            self._pending = []
        return out
