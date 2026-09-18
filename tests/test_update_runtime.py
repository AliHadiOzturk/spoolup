import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeStreamer:
    def __init__(self, live):
        self.is_streaming = live


class FakeCtx:
    def __init__(self):
        self.banners = []


def _make_spoolup(live=False):
    from spoolup.main import SpoolUp
    su = SpoolUp.__new__(SpoolUp)
    su.streamer = FakeStreamer(live)
    su.dashboard_ctx = FakeCtx()
    su._pending_restart = False
    su._update_running = False
    import threading
    su._update_runner_lock = threading.Lock()
    su.updater = None
    return su


def test_is_streaming_now():
    su = _make_spoolup(live=True)
    assert su._is_streaming_now() is True
    su.streamer = None
    assert su._is_streaming_now() is False


def test_stage_restart_defers_while_streaming():
    su = _make_spoolup(live=True)
    state = {}
    class U:
        def set_state(self, **v): state.update(v)
    su.updater = U()
    su._stage_restart_if_needed({"changed": True})
    assert su._pending_restart is True
    assert state["pending_restart"] is True
    assert any("staged" in b for b in su.dashboard_ctx.banners)


def test_maybe_restart_executes_at_standby():
    su = _make_spoolup(live=False)
    su._pending_restart = True
    calls = []
    su.restart_app = lambda: calls.append(1)
    su._maybe_restart_pending()
    assert calls == [1]


def test_maybe_restart_skips_when_streaming():
    su = _make_spoolup(live=True)
    su._pending_restart = True
    calls = []
    su.restart_app = lambda: calls.append(1)
    su._maybe_restart_pending()
    assert calls == []


def test_stage_restart_no_change_no_pending():
    su = _make_spoolup(live=False)
    class U:
        def set_state(self, **v): pass
    su.updater = U()
    calls = []
    su.restart_app = lambda: calls.append(1)
    su._stage_restart_if_needed({"changed": False})
    assert calls == []  # nothing staged, nothing to do


def test_stream_stop_fires_pending_restart():
    class StopStreamer:
        def __init__(self):
            self.is_streaming = True
        def stop_streaming(self):
            self.is_streaming = False
    class Req:
        kind = "stream_stop"
        payload = {}
    su = _make_spoolup(live=True)
    su.streamer = StopStreamer()
    su._pending_restart = True
    calls = []
    su.restart_app = lambda: calls.append(1)
    su._handle_dashboard_action(Req())
    assert calls == [1]


def test_checker_disabled_still_creates_updater():
    from spoolup.main import SpoolUp
    su = SpoolUp.__new__(SpoolUp)
    tmp = tempfile.mkdtemp()
    values = {"auto_update_enabled": False, "data_dir": tmp}
    class Cfg:
        def get(self, k, default=None):
            return values.get(k, default)
    su.config = Cfg()
    su.dashboard_ctx = FakeCtx()
    su._pending_restart = False
    su._update_checker_thread = None
    su.updater = None
    su._start_update_checker()
    assert su.updater is not None
    assert su._update_checker_thread is None


if __name__ == "__main__":
    test_is_streaming_now()
    test_stage_restart_defers_while_streaming()
    test_maybe_restart_executes_at_standby()
    test_maybe_restart_skips_when_streaming()
    test_stage_restart_no_change_no_pending()
    test_stream_stop_fires_pending_restart()
    test_checker_disabled_still_creates_updater()
    print("test_update_runtime: ALL PASS")
