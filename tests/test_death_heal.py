import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup import main as main_mod
from spoolup.main import SpoolUp, StreamManager


class _FakeConfig:
    def __init__(self):
        self.loaded = 0

    def load(self):
        self.loaded += 1

    def get(self, key, default=None):
        return {"webcam_url": "http://cam.local/stream"}.get(key, default)


class _FakeWatchdog:
    def __init__(self):
        self.checks = {}

    def register_check(self, name, fn):
        self.checks[name] = fn


def _make_manager():
    """StreamManager in the post-death state (monitor cleared is_streaming)."""
    s = StreamManager.__new__(StreamManager)
    s.config = _FakeConfig()
    s.stream_url = "rtmp://ingest/live/key"
    s.live_stream = {"id": "stream-id"}
    s.is_streaming = False  # as left by _ffmpeg_monitor_loop's death branch
    s._stopping = False
    s._ffmpeg_died_unexpectedly = False
    s._kill_ffmpeg = lambda: None
    calls = {"ffmpeg_monitor": 0, "health_monitor": 0, "spawn": []}
    s._start_ffmpeg_monitor = lambda: calls.__setitem__(
        "ffmpeg_monitor", calls["ffmpeg_monitor"] + 1
    )
    s._start_health_monitor = lambda: calls.__setitem__(
        "health_monitor", calls["health_monitor"] + 1
    )
    return s, calls


def _run_without_sleep(fn):
    orig_sleep = main_mod.time.sleep
    main_mod.time.sleep = lambda *_a, **_k: None
    try:
        return fn()
    finally:
        main_mod.time.sleep = orig_sleep


def test_restart_success_restores_state_and_monitors():
    s, calls = _make_manager()
    s._spawn_pipeline = lambda url: calls["spawn"].append(url) or True
    result = _run_without_sleep(s._restart_ffmpeg_stream)
    assert result is True
    assert s.is_streaming is True, "heal must restore is_streaming"
    assert calls["ffmpeg_monitor"] == 1, "ffmpeg monitor must be restarted"
    assert calls["health_monitor"] == 1, "health monitor must be restarted"
    assert calls["spawn"] == ["http://cam.local/stream"]
    assert s.config.loaded == 1, "config must be reloaded on restart"
    assert s._stopping is False


def test_restart_success_without_live_stream_skips_health_monitor():
    s, calls = _make_manager()
    s.live_stream = None
    s._spawn_pipeline = lambda url: True
    result = _run_without_sleep(s._restart_ffmpeg_stream)
    assert result is True
    assert s.is_streaming is True
    assert calls["ffmpeg_monitor"] == 1
    assert calls["health_monitor"] == 0, "no health monitor without live_stream"


def test_restart_spawn_failure_returns_false_and_leaves_state():
    s, calls = _make_manager()
    s._spawn_pipeline = lambda url: False
    result = _run_without_sleep(s._restart_ffmpeg_stream)
    assert result is False
    assert s.is_streaming is False, "failed heal must not claim streaming"
    assert calls["ffmpeg_monitor"] == 0
    assert calls["health_monitor"] == 0
    assert s._stopping is False


def test_restart_without_stream_url_returns_false():
    s, calls = _make_manager()
    s.stream_url = None
    s._spawn_pipeline = lambda url: calls["spawn"].append(url) or True
    result = _run_without_sleep(s._restart_ffmpeg_stream)
    assert result is False
    assert s.is_streaming is False
    assert calls["spawn"] == [], "spawn must not run without a stream URL"
    assert calls["ffmpeg_monitor"] == 0
    assert calls["health_monitor"] == 0


def test_watchdog_heal_clears_flag_and_restores_streaming():
    """Wiring contract of check_ffmpeg's heal: after heal_fn runs, the death
    flag is cleared AND is_streaming is True again."""
    s = StreamManager.__new__(StreamManager)
    s._ffmpeg_died_unexpectedly = True  # set by monitor death branch
    s.is_streaming = False              # cleared by monitor death branch
    restarts = []

    def fake_restart():
        restarts.append(1)
        s.is_streaming = True  # fixed _restart_ffmpeg_stream contract
        return True

    s._restart_ffmpeg_stream = fake_restart

    sp = SpoolUp.__new__(SpoolUp)
    sp.streamer = s
    sp.watchdog = _FakeWatchdog()
    sp._register_watchdog_checks()

    outcome = sp.watchdog.checks["ffmpeg"]()
    assert outcome is not None, "death flag must surface an unhealthy check"
    ok, message, heal_fn = outcome
    assert ok is False
    assert "ffmpeg died" in message

    heal_fn()
    assert restarts == [1], "heal must call the restart exactly once"
    assert s._ffmpeg_died_unexpectedly is False, "heal must clear the flag"
    assert s.is_streaming is True, "after heal the runtime must read streaming"

    # Gate closes after heal: no further unhealthy reports.
    assert sp.watchdog.checks["ffmpeg"]() is None


if __name__ == "__main__":
    test_restart_success_restores_state_and_monitors()
    test_restart_success_without_live_stream_skips_health_monitor()
    test_restart_spawn_failure_returns_false_and_leaves_state()
    test_restart_without_stream_url_returns_false()
    test_watchdog_heal_clears_flag_and_restores_streaming()
    print("test_death_heal: ALL PASS")
