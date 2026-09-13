import sys, os, time, collections, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.frame_pump import FramePump, parse_boundary
from tests.mjpeg_util import make_jpeg


def test_parse_boundary_header_variants():
    assert parse_boundary('multipart/x-mixed-replace;boundary="abcd"') == b"abcd"
    assert parse_boundary("multipart/mixed; boundary=efgh") == b"efgh"
    assert parse_boundary("image/jpeg") is None
    assert parse_boundary("") is None


def _bare_pump(buffer_capacity: int, fps: int = 300) -> FramePump:
    pump = FramePump.__new__(FramePump)
    pump.fps = fps
    pump._interval = 1.0 / fps
    pump._buffer = collections.deque(maxlen=buffer_capacity)
    pump._last = None
    pump._lock = threading.Lock()
    pump._stop = threading.Event()
    pump._reader_thread = None
    pump._pacer_thread = None
    pump._response = None
    return pump


def test_buffer_drops_oldest_when_full():
    pump = _bare_pump(3)
    frames = [make_jpeg(i) for i in range(5)]
    for f in frames:
        pump._push_frame(f)
    assert list(pump._buffer) == frames[-3:], "drop-oldest keeps latency bounded"
    assert pump._last == frames[-1]


def test_pacer_never_starves_after_drain():
    pump = _bare_pump(3)
    pump._push_frame(make_jpeg(0))
    r, w = os.pipe()
    os.set_blocking(r, False)
    pump.serve(w)
    deadline = time.time() + 0.4
    out = b""
    while time.time() < deadline:
        try:
            out += os.read(r, 4096)
        except BlockingIOError:
            time.sleep(0.01)
    pump.stop()
    os.close(w)
    os.close(r)
    segments = out.split(b"\xff\xd9")[:-1]
    assert len(segments) >= 5, "pacer must keep flow after buffer empties"
    assert all(seg + b"\xff\xd9" == make_jpeg(0) for seg in segments), \
        "underflow ticks repeat the LAST frame, never stall"


if __name__ == "__main__":
    test_parse_boundary_header_variants()
    test_buffer_drops_oldest_when_full()
    test_pacer_never_starves_after_drain()
    print("test_frame_pump: ALL PASS")
