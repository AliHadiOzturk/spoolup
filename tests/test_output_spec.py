import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.main import StreamManager


class FakeConfig:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def make_spec(config: dict) -> str:
    sm = StreamManager.__new__(StreamManager)  # skip YouTube API init
    sm.config = config
    sm.stream_url = "rtmp://yt/YTKEY"
    return sm._build_output_spec()


def test_youtube_only():
    spec = make_spec(FakeConfig({"kick_enabled": False}))
    assert spec == "[f=flv:onfail=ignore]rtmp://yt/YTKEY"


def test_kick_enabled_appended():
    spec = make_spec(FakeConfig({
        "kick_enabled": True,
        "kick_stream_key": "kickkey123",
        "kick_rtmp_url": "rtmp://kick.example:1935/live/",
    }))
    assert spec == (
        "[f=flv:onfail=ignore]rtmp://yt/YTKEY|"
        "[f=flv:onfail=ignore]rtmp://kick.example:1935/live/kickkey123"
    )


def test_kick_missing_key_disabled():
    spec = make_spec(FakeConfig({"kick_enabled": True, "kick_stream_key": ""}))
    assert spec == "[f=flv:onfail=ignore]rtmp://yt/YTKEY"


def test_srt_with_embedded_streamid():
    spec = make_spec(FakeConfig({
        "kick_enabled": True,
        "kick_stream_key": "",
        "kick_rtmp_url": "srt://kick.srt.example:9000?streamid=sk_embedded",
    }))
    assert spec == (
        "[f=flv:onfail=ignore]rtmp://yt/YTKEY|"
        "[f=mpegts:onfail=ignore]srt://kick.srt.example:9000?streamid=sk_embedded"
    )


def test_srt_appends_streamid_when_key_given():
    spec = make_spec(FakeConfig({
        "kick_enabled": True,
        "kick_stream_key": "sk_live",
        "kick_rtmp_url": "srt://kick.srt.example:9000",
    }))
    assert spec == (
        "[f=flv:onfail=ignore]rtmp://yt/YTKEY|"
        "[f=mpegts:onfail=ignore]srt://kick.srt.example:9000?streamid=sk_live"
    )


def test_mask_key():
    assert StreamManager._mask_key("s3cret") == "s3cr***"
    assert StreamManager._mask_key("") == "<empty>"


if __name__ == "__main__":
    test_youtube_only()
    test_kick_enabled_appended()
    test_kick_missing_key_disabled()
    test_srt_with_embedded_streamid()
    test_srt_appends_streamid_when_key_given()
    test_mask_key()
    print("test_output_spec: ALL PASS")
