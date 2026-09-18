"""Local audio library + persisted playlist state for the dashboard."""

import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ALLOWED_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class AudioLibrary:
    """Track storage under <data_dir>/audio/."""

    def __init__(self, data_dir: str):
        self.audio_dir = os.path.join(data_dir, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)

    def _track_id(self, data: bytes) -> str:
        return hashlib.md5(data).hexdigest()[:8]

    def list_tracks(self) -> List[Dict[str, Any]]:
        tracks = []
        for name in sorted(os.listdir(self.audio_dir)):
            if not name.lower().endswith(ALLOWED_EXT):
                continue
            path = os.path.join(self.audio_dir, name)
            tracks.append({
                "id": name.split("__", 1)[0] if "__" in name else name,
                "name": name.split("__", 1)[-1],
                "size": os.path.getsize(path),
                "path": path,
            })
        return tracks

    def save_upload(self, filename: str, data: bytes) -> Dict[str, Any]:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXT:
            raise ValueError("unsupported audio format: %s" % ext)
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("file too large (max 50 MB)")
        track_id = self._track_id(data)
        stored = "%s__%s" % (track_id, os.path.basename(filename))
        path = os.path.join(self.audio_dir, stored)
        fd, tmp = tempfile.mkstemp(dir=self.audio_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {"id": track_id, "name": os.path.basename(filename),
                "size": len(data), "path": path}

    def delete_track(self, track_id: str) -> bool:
        for t in self.list_tracks():
            if t["id"] == track_id:
                os.unlink(t["path"])
                return True
        return False

    def track_path(self, track_id: str) -> Optional[str]:
        for t in self.list_tracks():
            if t["id"] == track_id:
                return t["path"]
        return None


class PlaylistState:
    """Persisted playlist/audio preferences (atomic JSON)."""

    DEFAULTS = {
        "source": "silence",
        "volume": 0.8,
        "loop": True,
        "order": [],
        "track": None,
        "spotify_uri": "",
    }

    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, Any]:
        values = dict(self.DEFAULTS)
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    values.update(json.load(f))
            except Exception as e:
                logger.warning("playlist state unreadable, using defaults: %s", e)
        return values

    def save(self, values: Dict[str, Any]) -> None:
        merged = dict(self.load())
        merged.update(values)
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(merged, f, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
