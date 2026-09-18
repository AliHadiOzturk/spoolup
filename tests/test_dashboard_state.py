import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.dashboard.state import DashboardRequest, RuntimeContext, RecentLogHandler


class FakeRuntime:
    def __init__(self):
        self.is_streaming = False
        self.watch_url = None
        self.streamer = None
        self.moonraker = None


class FakeStreamer:
    def __init__(self):
        self.is_streaming = True
        self.stream_url = "rtmp://yt/YTKEY"
        self.live_broadcast = {"id": "b1"}
        self.frame_pump = None
        self.last_health = "good"

    def get_watch_url(self):
        return "https://youtube.com/watch?v=b1"


def make_cfg(extra=None):
    cfg = {
        "dashboard_enabled": True,
        "dashboard_host": "127.0.0.1",
        "dashboard_port": 8007,
        "kick_enabled": True,
        "kick_stream_key": "supersecret1234",
        "webcam_url": "http://printer:8080/?action=stream",
        "moonraker_url": "http://printer:7125",
    }
    if extra:
        cfg.update(extra)
    return cfg


def make_ctx(cfg=None, runtime=None):
    cfg = cfg if cfg is not None else make_cfg()
    rt = runtime if runtime is not None else FakeRuntime()
    return RuntimeContext(
        runtime=rt,
        config_get=cfg.get,
        config_keys=list(cfg.keys()),
        secret_keys=["kick_stream_key"],
        config_file="/tmp/test/config.json",
        save_config=lambda values: True,
        test_webcam=lambda url: url.startswith("http"),
        test_moonraker=lambda url: url.startswith("http"),
    ), rt


def test_status_snapshot_with_streamer():
    ctx, _ = make_ctx(runtime=FakeRuntime())
    ctx.runtime.streamer = FakeStreamer()
    ctx.runtime.is_streaming = True
    s = ctx.status()
    assert s["stream"]["is_streaming"] is True
    assert s["stream"]["watch_url"] == "https://youtube.com/watch?v=b1"
    assert s["stream"]["sinks"]["youtube"]["health"] == "good"
    assert s["stream"]["sinks"]["kick"]["configured"] is True
    assert s["uptime_seconds"] >= 0
    assert isinstance(s["banners"], list)


def test_status_snapshot_minimal_runtime():
    ctx, rt = make_ctx()
    s = ctx.status()
    assert s["stream"]["is_streaming"] is False
    assert s["stream"]["watch_url"] is None
    assert s["stream"]["pump"] is None


def test_mask_config():
    ctx, _ = make_ctx()
    masked = ctx.mask_config(ctx.config_values())
    assert masked["kick_stream_key"] == "***"
    assert masked["dashboard_port"] == 8007


def test_recent_log_handler_ring():
    h = RecentLogHandler(limit=3)
    h.setFormatter(logging.Formatter("%(message)s"))
    lg = logging.getLogger("ring")
    lg.setLevel(logging.INFO)
    lg.addHandler(h)
    for i in range(5):
        lg.info("line %d", i)
    lines = h.tail()
    assert lines == ["line 2", "line 3", "line 4"]


def test_action_queue_single_flight():
    ctx, _ = make_ctx()
    assert ctx.submit(DashboardRequest(kind="stream_restart")) is True
    assert ctx.submit(DashboardRequest(kind="stream_stop")) is False
    drained = ctx.drain_actions()
    assert [r.kind for r in drained] == ["stream_restart"]
    # re-armed now
    assert ctx.submit(DashboardRequest(kind="stream_stop")) is True


if __name__ == "__main__":
    test_status_snapshot_with_streamer()
    test_status_snapshot_minimal_runtime()
    test_mask_config()
    test_recent_log_handler_ring()
    test_action_queue_single_flight()
    print("test_dashboard_state: ALL PASS")
