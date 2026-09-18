import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from spoolup.dashboard.state import RuntimeContext


class FakeRuntime:
    is_streaming = False
    streamer = None
    moonraker = None


class FakeStreamer:
    is_streaming = True
    stream_url = "rtmp://yt/K"
    live_broadcast = {"id": "b1"}
    last_health = "good"
    frame_pump = None

    def get_watch_url(self):
        return "https://youtube.com/watch?v=b1"


def make_client(secret_keys=None):
    from spoolup.dashboard.app import create_app, INT_KEYS

    cfg = {
        "dashboard_enabled": True, "dashboard_host": "127.0.0.1",
        "dashboard_port": 8007, "kick_enabled": True,
        "kick_stream_key": "supersecret1234",
        "webcam_url": "http://p:8080/?action=stream",
        "moonraker_url": "http://p:7125", "stream_fps": 30,
        "kick_rtmp_url": "srt://k:9000", "ingest_buffer_seconds": 10,
        "stream_bitrate": "4500k", "stream_resolution": "1280x720",
        "timelapse_dir": "/tmp/tl", "timelapse_mode": "local",
        "printer_ip": "192.168.1.115", "moonraker_port": "7125",
        "youtube_category_id": "28", "video_privacy": "private",
        "stream_privacy": "unlisted", "enable_live_stream": True,
        "enable_timelapse_upload": True, "disable_ssl_verify": False,
        "watchdog_interval": 5, "auto_update_interval_h": 24,
        "retry_attempts": 3,
        "token_file": "/tmp/test/youtube_token.json",
    }
    os.makedirs("/tmp/test", exist_ok=True)
    if not os.path.exists("/tmp/test/config.json"):
        with open("/tmp/test/config.json", "w") as f:
            f.write("{}")
    rt = FakeRuntime()
    ctx = RuntimeContext(
        runtime=rt,
        config_get=cfg.get,
        config_keys=list(cfg.keys()),
        secret_keys=secret_keys or ["kick_stream_key"],
        config_file="/tmp/test/config.json",
        save_config=lambda values: True,
        test_webcam=lambda url: url.startswith("http"),
        test_moonraker=lambda url: url.startswith("http"),
    )
    ctx.runtime.streamer = FakeStreamer()
    ctx.runtime.is_streaming = True
    return TestClient(create_app(ctx)), ctx, cfg, INT_KEYS


def test_dashboard_page_renders():
    client, _, _, _ = make_client()
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_status_not_leaking_secrets():
    client, _, _, _ = make_client()
    text = client.get("/api/status").text
    assert "supersecret1234" not in text


def test_stream_status_visible():
    client, _, _, _ = make_client()
    body = client.get("/api/status").json()
    s = body["stream"]
    assert s["is_streaming"] is True
    assert s["watch_url"] == "https://youtube.com/watch?v=b1"
    assert s["sinks"]["kick"]["configured"] is True


def test_logs_page_and_api():
    client, ctx, _, _ = make_client()
    ctx.log_handler._buffer.append("harness log line")
    assert "lines" in client.get("/api/logs?limit=10").json()
    assert client.get("/logs").status_code == 200


def test_config_get_masks_secret():
    client, _, _, _ = make_client()
    body = client.get("/api/config").json()
    assert body["kick_stream_key"] == "***"
    assert body["dashboard_port"] == 8007


def test_config_put_masks_sentinel_unchanged_and_saves():
    client, ctx, cfg, _ = make_client()
    saved = {}
    ctx.save_config = lambda values: saved.update(values) or True
    body = dict(cfg)
    body["kick_stream_key"] = "***"          # user did not touch the secret
    body["stream_fps"] = 15                  # user changed this
    r = client.put("/api/config", json=body)
    assert r.json()["ok"] is True
    assert "kick_stream_key" not in saved    # masked value NOT persisted
    assert saved["stream_fps"] == 15


def test_config_put_rejects_bad_int_type():
    client, _, _, _ = make_client()
    r = client.put("/api/config", json={"stream_fps": "abc"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_config_put_rejects_unknown_key():
    client, _, _, _ = make_client()
    r = client.put("/api/config", json={"definitely_not_a_key": 1})
    assert r.status_code == 400


def test_settings_put_accepts_string_ints_from_form():
    client, _, _, INT_KEYS = make_client()
    # API stays strictly typed: a raw-string int must be rejected.
    r = client.put("/api/config", json={"stream_fps": "15"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    # The page coerces: every INT_KEY input is tagged data-int="1".
    html = client.get("/settings").text
    for key in INT_KEYS:
        assert ('data-key="%s"' % key) in html, key
        m = re.search(r'data-key="%s"[^>]*data-int="1"' % key, html)
        assert m, "missing data-int=1 for %s" % key
    # And the page-consistent (parseInt'd) payload is accepted.
    ok = client.put("/api/config", json={"stream_fps": 15})
    assert ok.json()["ok"] is True


def test_put_strips_ctx_secret_keys():
    # ctx-only secret (not in any app-level hardcoded list) must be stripped.
    client, ctx, _, _ = make_client(
        secret_keys=["kick_stream_key", "client_secrets_file"])
    assert "client_secrets_file" in ctx.secret_keys()
    saved = {}
    ctx.save_config = lambda values: saved.update(values) or True
    r = client.put("/api/config",
                   json={"client_secrets_file": "***", "stream_fps": 20})
    assert r.json()["ok"] is True
    assert "client_secrets_file" not in saved
    assert saved["stream_fps"] == 20


def test_wizard_redirect_when_no_config():
    client, ctx, _, _ = make_client()
    ctx.config_file = "/tmp/test/missing.json"
    r = client.get("/")
    assert r.status_code == 200
    assert "wizard" in r.text.lower()


def test_dashboard_when_config_exists():
    client, ctx, _, _ = make_client()
    assert os.path.exists(ctx.config_file)
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_wizard_token_upload_atomic(tmp=1):
    client, ctx, _, _ = make_client()
    ctx.config_file = str(os.path.join("/", "tmp", "test", "config.json"))
    files = {"token": ("youtube_token.json", b"CREDENTIALS-JSON-BYTES")}
    r = client.post("/api/wizard/token", files=files)
    assert r.json()["ok"] is True
    with open("/tmp/test/youtube_token.json", "rb") as f:
        assert f.read() == b"CREDENTIALS-JSON-BYTES"


def test_probe_endpoints():
    client, _, _, _ = make_client()
    ok = client.post("/api/config/test-webcam",
                     json={"url": "http://x/?action=stream"})
    assert ok.json() == {"ok": True}
    bad = client.post("/api/config/test-webcam", json={"url": "ftp://x"})
    assert bad.json() == {"ok": False}
    mr = client.post("/api/config/test-moonraker",
                     json={"url": "http://x:7125"})
    assert mr.json() == {"ok": True}


def test_dashboard_thread_serves_http():
    # Empirical proof for C1: uvicorn.Server started via server.run in a
    # daemon thread actually answers HTTP (server.serve would not).
    import json
    import socket
    import threading
    import time
    import urllib.request

    import uvicorn

    from spoolup.dashboard.app import create_app

    # Reserve an ephemeral free port so a bind failure from "port busy"
    # is near-impossible and the test cannot silently skip.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    _, ctx, _, _ = make_client()
    config = uvicorn.Config(create_app(ctx), host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True,
                              name="test-dashboard")
    thread.start()
    body = None
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/status" % port,
                        timeout=2) as resp:
                    if resp.status == 200:
                        body = resp.read().decode()
                        break
            except Exception:
                time.sleep(0.1)
        assert thread.is_alive(), (
            "dashboard thread died before serving HTTP; if the thread target "
            "regressed to server.serve (a coroutine function), the thread "
            "exits immediately without ever binding")
        assert body is not None, "dashboard thread did not serve HTTP"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    data = json.loads(body)
    assert data["stream"]["is_streaming"] is True
    assert "banners" in data


if __name__ == "__main__":
    test_dashboard_page_renders()
    test_status_not_leaking_secrets()
    test_stream_status_visible()
    test_logs_page_and_api()
    test_config_get_masks_secret()
    test_config_put_masks_sentinel_unchanged_and_saves()
    test_config_put_rejects_bad_int_type()
    test_config_put_rejects_unknown_key()
    test_settings_put_accepts_string_ints_from_form()
    test_put_strips_ctx_secret_keys()
    test_wizard_redirect_when_no_config()
    test_dashboard_when_config_exists()
    test_wizard_token_upload_atomic()
    test_probe_endpoints()
    test_dashboard_thread_serves_http()
    print("test_dashboard_app: ALL PASS")
