"""Print-session history store (data/sessions.json, capped at 50)."""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SESSIONS = 50


class SessionStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._next_id = 1

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.warning("sessions file unreadable, starting fresh: %s", e)
        return []

    def _save(self, sessions: List[Dict[str, Any]]) -> None:
        sessions = sessions[-MAX_SESSIONS:]
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(sessions, f, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def record_start(
        self, filename: str, started_at: str, platforms: List[str]
    ) -> int:
        with self._lock:
            sessions = self._load()
            session_id = sessions[-1]["id"] + 1 if sessions else 1
            sessions.append({
                "id": session_id,
                "filename": filename,
                "started_at": started_at,
                "ended_at": None,
                "outcome": None,
                "platforms": list(platforms),
                "upload": None,
            })
            self._save(sessions)
        return session_id

    def record_end(self, session_id: int, outcome: str) -> None:
        with self._lock:
            sessions = self._load()
            for sess in reversed(sessions):
                if sess["id"] == session_id:
                    sess["outcome"] = outcome
                    sess["ended_at"] = datetime.now(timezone.utc).isoformat()
                    self._save(sessions)
                    return
        logger.warning("record_end: session %s not found", session_id)

    def record_upload(self, session_id: int, ok: bool, detail: str = "") -> None:
        with self._lock:
            sessions = self._load()
            for sess in reversed(sessions):
                if sess["id"] == session_id:
                    sess["upload"] = {"ok": bool(ok), "detail": detail}
                    self._save(sessions)
                    return
        logger.warning("record_upload: session %s not found", session_id)

    def list_recent(self, limit: int = MAX_SESSIONS) -> List[Dict[str, Any]]:
        return list(reversed(self._load()))[:limit]
