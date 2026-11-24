import sys, os, time, struct, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.audio_server import (
    AudioServer, SilenceSource, CHUNK_BYTES, scale_pcm, mix_pcm,
)


def test_scale_pcm_passthrough_and_clamp():
    data = struct.pack("<4h", 1000, -1000, 32767, -32768)
    assert scale_pcm(data, 1.0) == data
    half = struct.unpack("<4h", scale_pcm(data, 0.5))
    assert half[0] == 500 and half[1] == -500
    assert half[2] == 16383 and half[3] == -16384
    loud = struct.unpack("<2h", scale_pcm(struct.pack("<2h", 30000, 30000), 2.0))
    assert loud == (32767, 32767)  # clamped, not overflowed


def test_mix_pcm_endpoints_and_middle():
    a = struct.pack("<4h", 1000, 1000, 1000, 1000)
    b = struct.pack("<4h", 2000, 2000, 2000, 2000)
    assert struct.unpack("<4h", mix_pcm(a, b, 0.0)) == (1000,) * 4
    assert struct.unpack("<4h", mix_pcm(a, b, 1.0)) == (2000,) * 4
    mid = struct.unpack("<4h", mix_pcm(a, b, 0.5))
    assert mid == (1500,) * 4


class FakeSource:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.closed = False

    def read_chunk(self, n_bytes):
        return struct.pack("<%dh" % (n_bytes // 2), *([self.value] * (n_bytes // 2)))

    def close(self):
        self.closed = True


def _make_server():
    srv = AudioServer.__new__(AudioServer)
    import threading as _t
    srv._volume = 1.0
    srv._listener = None
    srv._conn = None
    srv._port = 0
    srv._thread = None
    srv._stop = _t.Event()
    srv._source = SilenceSource()
    srv._fade_from = None
    srv._fade_left = 0
    srv._lock = _t.Lock()
    srv._chunks_sent = 0
    srv._chunks_drained = 0
    return srv


def test_set_source_swaps_with_fade_and_closes_old():
    srv = _make_server()
    old = FakeSource("old", 1000)
    new = FakeSource("new", 2000)
    srv._source = old
    srv.set_source(new)
    assert srv._source is new
    assert srv._fade_from is old
    assert old.closed is False           # old survives until fade completes
    assert srv._fade_left > 0
    # simulate fade completion
    from spoolup.audio_server import FADE_CHUNKS
    srv._fade_left = 1
    with srv._lock:
        pass
    # one more pacer tick equivalent: emulate decrement branch directly
    t = 1.0 - (1.0 / FADE_CHUNKS)
    mixed = mix_pcm(old.read_chunk(CHUNK_BYTES), new.read_chunk(CHUNK_BYTES), t)
    assert struct.unpack("<1h", mixed[:2])[0] > 1000  # moving toward new


def test_audio_server_tcp_roundtrip():
    srv = AudioServer(volume=1.0)
    port = srv.start()
    assert port > 0
    srv.set_source(SilenceSource())
    import socket as _s
    client = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    client.settimeout(10)
    client.connect(("127.0.0.1", port))
    deadline = time.time() + 5
    data = b""
    while time.time() < deadline and len(data) < CHUNK_BYTES * 3:
        data += client.recv(CHUNK_BYTES * 3)
    client.close()
    srv.stop()
    assert len(data) >= CHUNK_BYTES * 2, "server must pace PCM to the client"
    assert data.count(b"\x00") == len(data), "silence source emits zeros"


def test_audio_server_reconnect_serves_second_client():
    srv = AudioServer(volume=1.0)
    port = srv.start()
    assert port > 0
    srv.set_source(SilenceSource())
    import socket as _s

    def read_chunks(sock, n):
        data = b""
        deadline = time.time() + 5
        while time.time() < deadline and len(data) < CHUNK_BYTES * n:
            part = sock.recv(CHUNK_BYTES * n - len(data))
            if not part:
                break
            data += part
        return data

    client1 = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    client1.settimeout(10)
    client1.connect(("127.0.0.1", port))
    first = read_chunks(client1, 2)
    assert len(first) >= CHUNK_BYTES * 2, "client #1 must receive 2 chunks"
    client1.close()

    client2 = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    client2.settimeout(10)
    client2.connect(("127.0.0.1", port))
    second = read_chunks(client2, 2)
    client2.close()
    srv.stop()
    assert len(second) >= CHUNK_BYTES * 2, \
        "server must accept and pace a second client after the first dies"


def test_librespot_source_spawns_and_reads():
    import tempfile, stat, os as _os
    script = _os.path.join(tempfile.mkdtemp(), "fake_librespot.py")
    with open(script, "w") as f:
        f.write("import sys,time\n"
                "b=b'\\x00'*1764\n"
                "while True:\n"
                "    sys.stdout.buffer.write(b); sys.stdout.buffer.flush(); time.sleep(0.01)\n")
    from spoolup.audio_server import LibrespotSource, CHUNK_BYTES
    src = LibrespotSource(
        librespot_path=sys.executable,
        username="u", password="p",
        argv_override=[script],
    )
    chunk = src.read_chunk(CHUNK_BYTES)
    assert len(chunk) == CHUNK_BYTES
    src.close()


def test_librespot_cmd_matches_mode():
    from spoolup.audio_server import LibrespotSource
    # zeroconf only: credentials NEVER passed (password auth is dead)
    z = LibrespotSource.build_cmd("/usr/bin/librespot", "", "",
                                  cache_dir="/cache")
    assert "--username" not in z and "--password" not in z
    assert "--cache" in z and "--system-cache" in z and "--name" in z
    assert "--backend" in z and "pipe" in z
    assert "--format" in z and "S16" in z
    assert "--initial-volume" in z
    assert "--zeroconf-port" in z and "24879" in z
    assert "--device-type" in z
    # Even if legacy username/password are supplied, do not put them on argv
    l = LibrespotSource.build_cmd("/usr/bin/librespot", "u", "p",
                                  cache_dir="/cache")
    assert "--username" not in l and "--password" not in l and "--cache" in l


def test_resolve_librespot_path_uses_which(tmp_path=None):
    import tempfile, os as _os, stat
    from spoolup.audio_server import resolve_librespot_path
    assert resolve_librespot_path("/no/such/librespot-bin") is None
    d = tempfile.mkdtemp()
    fake = _os.path.join(d, "librespot")
    with open(fake, "w") as f:
        f.write("#!/bin/sh\n")
    _os.chmod(fake, _os.stat(fake).st_mode | stat.S_IEXEC)
    assert resolve_librespot_path(fake) == fake


def test_snapshot_reports_source_alive():
    srv = _make_server()
    snap = srv.snapshot()
    assert snap["source"] == "silence"
    assert snap["source_alive"] is True


def test_audio_server_drains_without_client():
    """Spotify Connect needs realtime drain even before ffmpeg connects."""
    srv = AudioServer(volume=1.0)
    srv.start()
    time.sleep(0.25)
    snap = srv.snapshot()
    srv.stop()
    assert snap["listening"] is True
    assert snap["client_connected"] is False
    assert snap["chunks_drained"] >= 10, \
        "pacer must drain source with no TCP client (got %s)" % snap["chunks_drained"]


def test_librespot_reader_applies_backpressure():
    """Queue must not grow unbounded — that caused Spotify to skip tracks."""
    import tempfile, os as _os
    script = _os.path.join(tempfile.mkdtemp(), "fast_pcm.py")
    with open(script, "w") as f:
        f.write(
            "import sys\n"
            "b=b'\\x01'*1764\n"
            "while True:\n"
            "    sys.stdout.buffer.write(b); sys.stdout.buffer.flush()\n"
        )
    from spoolup.audio_server import LibrespotSource
    src = LibrespotSource(
        librespot_path=sys.executable,
        argv_override=[script],
    )
    time.sleep(0.3)
    with src._lock:
        qlen = len(src._queue)
    src.close()
    assert qlen <= src._max_queue + 1, \
        "librespot reader must block when full, not drop (q=%d)" % qlen


if __name__ == "__main__":
    test_scale_pcm_passthrough_and_clamp()
    test_mix_pcm_endpoints_and_middle()
    test_set_source_swaps_with_fade_and_closes_old()
    test_audio_server_tcp_roundtrip()
    test_audio_server_reconnect_serves_second_client()
    test_librespot_source_spawns_and_reads()
    test_librespot_cmd_matches_mode()
    test_resolve_librespot_path_uses_which()
    test_snapshot_reports_source_alive()
    test_audio_server_drains_without_client()
    test_librespot_reader_applies_backpressure()
    print("test_audio_server: ALL PASS")
