import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from spoolup.dashboard.state import RuntimeContext, DashboardRequest


class FakeAudioServer:
    def __init__(self):
        self.source_name = "silence"
        self.volume = 0.8
        self.set_calls = []

    def snapshot(self):
        return {"source": self.source_name, "volume": self.volume,
                "port": 9999, "listening": True, "client_connected": False}

    def set_source(self, source):
        self.set_calls.append(source.name)
        self.source_name = source.name

    def set_volume(self, v):
        self.volume = v


def make_client_with_audio():
    from spoolup.dashboard.app import create_app
    from spoolup.audio_library import AudioLibrary, PlaylistState
    import tempfile

    d = tempfile.mkdtemp(prefix="spoolup-dash-audio-")
    lib = AudioLibrary(d)
    plist = PlaylistState(os.path.join(d, "playlist.json"))
    audio = FakeAudioServer()

    cfg = {"dashboard_enabled": True, "dashboard_port": 8007,
           "kick_stream_key": "k", "audio_server_enabled": True,
           "data_dir": d, "stream_fps": 30, "ingest_buffer_seconds": 10}

    class RT:
        streamer = None
        moonraker = None
        is_streaming = False

    ctx = RuntimeContext(
        runtime=RT(),
        config_get=cfg.get,
        config_keys=list(cfg.keys()),
        secret_keys=["kick_stream_key", "spotify_password"],
        config_file="/tmp/test/config.json",
        save_config=lambda v: True,
        test_webcam=lambda u: True,
        test_moonraker=lambda u: True,
    )
    ctx.audio_library = lib
    ctx.playlist_state = plist
    ctx.get_audio_server = lambda: audio
    client = TestClient(create_app(ctx))
    return client, ctx, lib, audio


def test_audio_status_endpoint():
    client, _, _, _ = make_client_with_audio()
    body = client.get("/api/audio/status").json()
    assert body["snapshot"]["source"] == "silence"
    assert body["snapshot"]["volume"] == 0.8


def test_music_upload_list_delete():
    client, _, lib, _ = make_client_with_audio()
    r = client.post("/api/music/tracks",
                    files={"file": ("song.mp3", b"FAKE-BYTES")})
    assert r.status_code == 200
    track = r.json()
    assert track["name"] == "song.mp3"
    listed = client.get("/api/music/tracks").json()
    assert any(t["id"] == track["id"] for t in listed)
    r = client.delete("/api/music/tracks/" + track["id"])
    assert r.json()["ok"] is True


def test_music_upload_rejects_bad_ext():
    client, _, _, _ = make_client_with_audio()
    r = client.post("/api/music/tracks",
                    files={"file": ("evil.exe", b"MZ")})
    assert r.status_code == 400


def test_audio_source_action_queued():
    client, ctx, _, _ = make_client_with_audio()
    r = client.post("/api/audio/source",
                    json={"source": "library", "track_id": "abc12345"})
    assert r.json()["ok"] is True
    reqs = ctx.drain_actions()
    assert [q.kind for q in reqs] == ["audio_source"]
    assert reqs[0].payload["track_id"] == "abc12345"


def test_audio_volume_action_queued():
    client, ctx, _, _ = make_client_with_audio()
    r = client.post("/api/audio/volume", json={"volume": 0.3})
    reqs = ctx.drain_actions()
    assert reqs[0].kind == "audio_volume"
    assert reqs[0].payload["volume"] == 0.3


def test_music_page_renders():
    client, _, _, _ = make_client_with_audio()
    assert client.get("/music").status_code == 200


if __name__ == "__main__":
    test_audio_status_endpoint()
    test_music_upload_list_delete()
    test_music_upload_rejects_bad_ext()
    test_audio_source_action_queued()
    test_audio_volume_action_queued()
    test_music_page_renders()
    print("test_audio_dashboard: ALL PASS")
