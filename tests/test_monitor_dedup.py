import sys, os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup import main as main_mod
from spoolup.main import StreamManager


class _FakeConfig:
    def __init__(self):
        self.loaded = 0

    def load(self):
        self.loaded += 1

    def get(self, key, default=None):
        return {"webcam_url": "http://cam.local/stream"}.get(key, default)


def _make_manager():
    """StreamManager with the REAL _start_*_monitor methods (dedup under test)."""
    s = StreamManager.__new__(StreamManager)
    s.config = _FakeConfig()
    s.stream_url = "rtmp://ingest/live/key"
    s.live_stream = {"id": "stream-id"}
    s.is_streaming = False
    s._stopping = False
    s._ffmpeg_died_unexpectedly = False
    s._kill_ffmpeg = lambda: None
    s._spawn_pipeline = lambda url: True
    s._health_check_thread = None
    s._ffmpeg_monitor_thread = None
    return s


def _live_sleeper(name, stop_event):
    t = threading.Thread(target=stop_event.wait, args=(30,), name=name, daemon=True)
    t.start()
    return t


def _alive_threads():
    return {t for t in threading.enumerate() if t.is_alive()}


def _run_restart(s):
    orig_sleep = main_mod.time.sleep
    main_mod.time.sleep = lambda *_a, **_k: None
    try:
        return s._restart_ffmpeg_stream()
    finally:
        main_mod.time.sleep = orig_sleep


def test_health_triggered_restart_does_not_duplicate_health_monitor():
    """Health loop alive at restart time: starter must no-op (exactly one)."""
    s = _make_manager()
    stop = threading.Event()
    fake_health = _live_sleeper("fake-health-check", stop)
    s._health_check_thread = fake_health
    # Also pin the ffmpeg monitor so its (real) starter no-ops too.
    fake_ffmpeg = _live_sleeper("fake-ffmpeg-monitor-a", stop)
    s._ffmpeg_monitor_thread = fake_ffmpeg
    before = _alive_threads()
    try:
        assert _run_restart(s) is True
        assert s._health_check_thread is fake_health, (
            "attribute must still refer to the original health thread"
        )
        live_health = [
            t for t in threading.enumerate() if t.name == "fake-health-check" and t.is_alive()
        ]
        assert len(live_health) == 1, "exactly one health thread must exist"
        assert _alive_threads() <= before, "restart must not spawn any new thread"
    finally:
        stop.set()
        fake_health.join(timeout=5)
        fake_ffmpeg.join(timeout=5)


def test_health_triggered_restart_does_not_duplicate_ffmpeg_monitor():
    """FFmpeg monitor alive at restart time: starter must no-op (exactly one)."""
    s = _make_manager()
    s.live_stream = None  # skip the health starter entirely in this test
    stop = threading.Event()
    fake_ffmpeg = _live_sleeper("fake-ffmpeg-monitor", stop)
    s._ffmpeg_monitor_thread = fake_ffmpeg
    before = _alive_threads()
    try:
        assert _run_restart(s) is True
        assert s._ffmpeg_monitor_thread is fake_ffmpeg, (
            "attribute must still refer to the original ffmpeg monitor thread"
        )
        live_ffmpeg = [
            t for t in threading.enumerate() if t.name == "fake-ffmpeg-monitor" and t.is_alive()
        ]
        assert len(live_ffmpeg) == 1, "exactly one ffmpeg monitor thread must exist"
        assert _alive_threads() <= before, "restart must not spawn any new thread"
    finally:
        stop.set()
        fake_ffmpeg.join(timeout=5)


if __name__ == "__main__":
    test_health_triggered_restart_does_not_duplicate_health_monitor()
    test_health_triggered_restart_does_not_duplicate_ffmpeg_monitor()
    print("test_monitor_dedup: ALL PASS")
