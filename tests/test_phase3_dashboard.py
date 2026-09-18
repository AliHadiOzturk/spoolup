import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


class RT:
    streamer = None
    moonraker = None


def make_client(mainsail_url=""):
    from spoolup.dashboard.app import create_app
    from spoolup.dashboard.state import RuntimeContext

    cfg = {"dashboard_enabled": True, "dashboard_port": 8007,
           "mainsail_url": mainsail_url, "stream_fps": 30,
           "watchdog_interval": 30, "keep_stream_on_error": True,
           "log_file": "data/spoolup.log",
           "ingest_buffer_seconds": 10}
    ctx = RuntimeContext(
        runtime=RT(),
        config_get=cfg.get,
        config_keys=list(cfg.keys()),
        secret_keys=["kick_stream_key"],
        config_file="/tmp/test/config.json",
        save_config=lambda v: True,
        test_webcam=lambda u: True,
        test_moonraker=lambda u: True,
    )
    return TestClient(create_app(ctx)), ctx


def test_sessions_endpoint_empty_when_unset():
    client, _ = make_client()
    body = client.get("/api/sessions").json()
    assert body == {"sessions": []}


def test_sessions_endpoint_lists_recent():
    client, ctx = make_client()
    import tempfile
    from spoolup.sessions import SessionStore
    d = tempfile.mkdtemp(prefix="phase3-")
    ctx.sessions = SessionStore(os.path.join(d, "sessions.json"))
    sid = ctx.sessions.record_start("part.gcode", "2026-09-14T10:00:00Z", ["youtube"])
    ctx.sessions.record_end(sid, "complete")
    body = client.get("/api/sessions").json()["sessions"]
    assert len(body) == 1
    assert body[0]["filename"] == "part.gcode"
    assert body[0]["outcome"] == "complete"


def test_printer_page_without_mainsail():
    client, _ = make_client(mainsail_url="")
    r = client.get("/printer")
    assert r.status_code == 200
    assert "mainsail_url" in r.text


def test_printer_page_with_mainsail():
    client, _ = make_client(mainsail_url="http://192.168.1.115:4408")
    r = client.get("/printer")
    assert r.status_code == 200
    assert "http://192.168.1.115:4408" in r.text
    assert "<iframe" in r.text


if __name__ == "__main__":
    test_sessions_endpoint_empty_when_unset()
    test_sessions_endpoint_lists_recent()
    test_printer_page_without_mainsail()
    test_printer_page_with_mainsail()
    print("test_phase3_dashboard: ALL PASS")
