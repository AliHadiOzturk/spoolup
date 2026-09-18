import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


class RT:
    streamer = None
    moonraker = None


def make_client(with_updater=True):
    from spoolup.dashboard.app import create_app
    from spoolup.dashboard.state import RuntimeContext

    cfg = {"dashboard_enabled": True, "dashboard_port": 8007,
           "stream_fps": 30, "ingest_buffer_seconds": 10,
           "auto_update_enabled": True, "auto_update_interval_h": 2}
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
    if with_updater:
        import tempfile
        from spoolup.updater import Updater
        d = tempfile.mkdtemp(prefix="update-dash-")
        ctx.updater = Updater(d, os.path.join(d, "state.json"))
        ctx.get_update_status = lambda: {
            "pending_restart": False,
            "last_check": {"ok": True, "ahead_by": 2,
                           "commits": [{"hash": "abc1234", "subject": "feat: x"},
                                       {"hash": "def5678", "subject": "fix: y"}]},
            "last_apply": None,
            "auto_update_enabled": True,
        }
    return TestClient(create_app(ctx)), ctx


def test_update_status_endpoint():
    client, _ = make_client()
    body = client.get("/api/update/status").json()
    assert body["pending_restart"] is False
    assert body["last_check"]["ahead_by"] == 2
    assert body["last_check"]["commits"][0]["subject"] == "feat: x"


def test_update_status_without_updater():
    client, _ = make_client(with_updater=False)
    body = client.get("/api/update/status").json()
    assert body.get("last_check") is None


def test_update_check_endpoint():
    client, _ = make_client()
    r = client.post("/api/update/check")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body


def test_update_apply_queues_action():
    client, ctx = make_client()
    r = client.post("/api/update/apply")
    assert r.json()["ok"] is True
    reqs = ctx.drain_actions()
    assert [q.kind for q in reqs] == ["update_apply"]


def test_status_includes_update():
    client, _ = make_client()
    body = client.get("/api/status").json()
    assert "update" in body
    assert body["update"]["last_check"]["ahead_by"] == 2


if __name__ == "__main__":
    test_update_status_endpoint()
    test_update_status_without_updater()
    test_update_check_endpoint()
    test_update_apply_queues_action()
    test_status_includes_update()
    print("test_update_dashboard: ALL PASS")
