"""Assert live-audio ffmpeg cmd keeps A/V from freezing RTMP."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.main import Config, StreamManager


class _FakeYoutube:
    pass


def _mgr() -> StreamManager:
    cfg = Config.__new__(Config)
    cfg._data = {
        "stream_resolution": "1280x720",
        "stream_fps": 30,
        "stream_bitrate": "4000k",
        "stream_buffer_size": "8000k",
        "kick_enabled": False,
        "stream_url": "rtmp://a.rtmp.youtube.com/live2/xxxx",
    }
    cfg.get = lambda key, default=None: cfg._data.get(key, default)
    mgr = StreamManager(cfg, _FakeYoutube())
    mgr._detect_h264_encoder = lambda: "libx264"  # type: ignore
    mgr.stream_url = "rtmp://a.rtmp.youtube.com/live2/xxxx"
    return mgr


def test_silent_audio_keeps_shortest():
    mgr = _mgr()
    cmd = mgr._build_ffmpeg_cmd("http://cam/", audio_port=None)
    assert "-shortest" in cmd
    assert "aresample=" not in " ".join(cmd)


def test_live_audio_uses_aresample_not_shortest():
    mgr = _mgr()
    cmd = mgr._build_ffmpeg_cmd("http://cam/", audio_port=12345)
    joined = " ".join(cmd)
    assert "-shortest" not in cmd
    assert "aresample=async=1:first_pts=0" in joined
    assert "tcp://127.0.0.1:12345" in joined
    assert cmd.count("-thread_queue_size") >= 2
    # Output CFR grid must be explicit so late frames still emit packets.
    assert "-r" in cmd
    assert cmd[cmd.index("-r") + 1] == "30"


if __name__ == "__main__":
    test_silent_audio_keeps_shortest()
    test_live_audio_uses_aresample_not_shortest()
    print("test_ffmpeg_av_sync: ALL PASS")
