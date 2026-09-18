import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.audio_library import AudioLibrary, PlaylistState
from spoolup.audio_server import FileSource, PlaylistSource, CHUNK_BYTES, silence_chunk


def _tmp():
    d = tempfile.mkdtemp(prefix="spoolup-audio-")
    os.makedirs(os.path.join(d, "data", "audio"), exist_ok=True)
    return d


def test_library_save_list_delete():
    d = _tmp()
    lib = AudioLibrary(d)
    track = lib.save_upload("song.mp3", b"FAKE-MP3-BYTES-1234")
    assert track["id"]
    assert track["name"] == "song.mp3"
    assert track["size"] == len(b"FAKE-MP3-BYTES-1234")
    tracks = lib.list_tracks()
    assert len(tracks) == 1
    assert lib.track_path(track["id"]).endswith(".mp3")
    assert lib.delete_track(track["id"]) is True
    assert lib.list_tracks() == []


def test_library_rejects_bad_types_and_size():
    d = _tmp()
    lib = AudioLibrary(d)
    try:
        lib.save_upload("evil.exe", b"MZ")
        assert False, "must reject non-audio extensions"
    except ValueError:
        pass
    try:
        lib.save_upload("big.mp3", b"x" * (50 * 1024 * 1024 + 1))
        assert False, "must reject >50MB"
    except ValueError:
        pass


def test_library_id_is_stable_and_unique():
    d = _tmp()
    lib = AudioLibrary(d)
    t1 = lib.save_upload("a.mp3", b"same-bytes")
    t2 = lib.save_upload("b.mp3", b"same-bytes")
    assert t1["id"] == t2["id"]  # content-addressed


def test_playlist_state_defaults_and_roundtrip():
    d = _tmp()
    st = PlaylistState(os.path.join(d, "playlist.json"))
    assert st.load()["source"] == "silence"
    assert st.load()["volume"] == 0.8
    st.save({"source": "library", "volume": 0.5, "loop": False,
             "order": ["x"], "track": "x", "spotify_uri": ""})
    assert st.load()["source"] == "library"
    assert st.load()["loop"] is False


def test_file_source_requires_ffmpeg_or_falls_back():
    # FileSource construction must not raise when ffmpeg is missing:
    # read_chunk returns silence instead (failsafe, logged).
    src = FileSource("/nonexistent/no.mp3")
    chunk = src.read_chunk(CHUNK_BYTES)
    assert len(chunk) == CHUNK_BYTES
    src.close()


def test_playlist_source_sequence_with_fake_process(monkey=None):
    # PlaylistSource with exhausted-injection: current EOF -> advance.
    src = PlaylistSource.__new__(PlaylistSource)
    import threading
    src._paths = ["/a.mp3", "/b.mp3"]
    src._loop = False
    src._idx = 0
    src._current = None
    src._lock = threading.Lock()

    class FakeFile:
        def __init__(self, name):
            self.name = name
            self.calls = 0
            self._eof = False
            self._queue = []
            self._proc = None

        def read_chunk(self, n):
            self.calls += 1
            if self.calls > 1:
                self._eof = True
            return b"\x01" * n

        def exhausted(self):
            return self._eof and not self._queue

        def close(self):
            pass

    src._make = lambda p: FakeFile(p)
    c1 = src.read_chunk(CHUNK_BYTES)
    c2 = src.read_chunk(CHUNK_BYTES)   # current now exhausted after this
    c3 = src.read_chunk(CHUNK_BYTES)   # advances to b
    c4 = src.read_chunk(CHUNK_BYTES)   # b exhausted after this
    c5 = src.read_chunk(CHUNK_BYTES)   # loop False -> silence
    assert c1 == b"\x01" * CHUNK_BYTES
    assert c5 == silence_chunk(CHUNK_BYTES)
    src.close()


def test_playlist_source_no_livelock_when_all_fail():
    import time
    import threading
    src = PlaylistSource.__new__(PlaylistSource)
    src._paths = ["/a.mp3", "/b.mp3"]
    src._loop = True
    src._idx = 0
    src._current = None
    src._lock = threading.Lock()

    class FakeFile:
        def __init__(self, name):
            self.name = name
            self._eof = True
            self._queue = []
            self._proc = None

        def read_chunk(self, n):
            return b"\x00" * n

        def exhausted(self):
            return True

        def close(self):
            pass

    src._make = lambda p: FakeFile(p)
    start = time.time()
    chunk = src.read_chunk(CHUNK_BYTES)
    elapsed = time.time() - start
    assert chunk == silence_chunk(CHUNK_BYTES)
    assert elapsed < 1, "read_chunk must not livelock (took %.2fs)" % elapsed
    src.close()


if __name__ == "__main__":
    test_library_save_list_delete()
    test_library_rejects_bad_types_and_size()
    test_library_id_is_stable_and_unique()
    test_playlist_state_defaults_and_roundtrip()
    test_file_source_requires_ffmpeg_or_falls_back()
    test_playlist_source_sequence_with_fake_process()
    test_playlist_source_no_livelock_when_all_fail()
    print("test_audio_library: ALL PASS")
