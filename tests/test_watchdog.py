import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.watchdog import Watchdog


def test_healthy_check_no_heal():
    w = Watchdog.__new__(Watchdog)
    w.interval = 9999
    w._stop = threading.Event()
    w._thread = None
    w.banners = []
    w._checks = []
    healed = []
    w.register_check("ok", lambda: (True, "fine", lambda: healed.append(1)))
    w._run_checks()
    assert healed == []
    assert w.banners == []


def test_unhealthy_check_heals_and_banners():
    w = Watchdog.__new__(Watchdog)
    w.interval = 9999
    w._stop = threading.Event()
    w._thread = None
    w.banners = []
    w._checks = []
    healed = []
    w.register_check("bad", lambda: (False, "ffmpeg dead", lambda: healed.append(1)))
    w._run_checks()
    assert healed == [1]
    assert any("ffmpeg dead" in b for b in w.banners)


def test_check_exception_is_contained():
    w = Watchdog.__new__(Watchdog)
    w.interval = 9999
    w._stop = threading.Event()
    w._thread = None
    w.banners = []
    w._checks = []
    w.register_check("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    w._run_checks()  # must not raise


def test_skip_check_returns_none():
    w = Watchdog.__new__(Watchdog)
    w.interval = 9999
    w._stop = threading.Event()
    w._thread = None
    w.banners = []
    w._checks = []
    called = []
    w.register_check("skip", lambda: None)
    w._run_checks()
    assert w.banners == []


def test_thread_start_stop():
    w = Watchdog(interval=1)
    w.banners = []
    w.register_check("noop", lambda: None)
    w.start()
    time.sleep(2.2)  # at least one sweep
    w.stop()
    assert not (w._thread and w._thread.is_alive())


def test_thread_runs_sweep_periodically():
    w = Watchdog(interval=30)
    w.interval = 0.05  # post-construction override, bypasses the clamp
    calls = []
    w.register_check("count", lambda: calls.append(1) or None)
    w.start()
    time.sleep(0.3)
    w.stop()
    assert len(calls) >= 2, "expected >= 2 sweeps, got %d" % len(calls)


if __name__ == "__main__":
    test_healthy_check_no_heal()
    test_unhealthy_check_heals_and_banners()
    test_check_exception_is_contained()
    test_skip_check_returns_none()
    test_thread_start_stop()
    test_thread_runs_sweep_periodically()
    print("test_watchdog: ALL PASS")
