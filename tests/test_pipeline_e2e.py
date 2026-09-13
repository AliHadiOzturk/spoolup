import sys, os, time, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OUT_FILE = "/tmp/opencode/_pump_e2e_out.bin"


def synthetic_jpegs(count: int):
    """Real decodable JPEGs via lavfi; fallback if ffmpeg missing."""
    try:
        raw = subprocess.run(
            [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
                "-frames:v", str(count), "-c:v", "mjpeg", "-f", "image2pipe", "-",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, timeout=30,
        ).stdout
        frames = raw.split(b"\xff\xd9")[:-1]
        return [f + b"\xff\xd9" for f in frames]
    except Exception:
        from tests.mjpeg_util import make_jpeg
        return [make_jpeg(i % 256, payload_size=200) for i in range(count)]


def main():
    import threading
    import collections
    from spoolup.frame_pump import FramePump

    frames = synthetic_jpegs(60)
    assert frames, "synthetic source failed"

    pump = FramePump.__new__(FramePump)
    pump.fps = 60
    pump._interval = 1.0 / pump.fps
    pump._buffer = collections.deque(maxlen=64)
    pump._lock = threading.Lock()
    pump._last = None
    pump._stop = threading.Event()
    pump._reader_thread = None
    pump._pacer_thread = None
    pump._response = None
    pump._stats_lock = threading.Lock()
    pump._stats_frames_read = 0
    pump._stats_bytes_read = 0
    pump._stats_frames_stale_dropped = 0
    pump._stats_frames_paced = 0
    pump._stats_frames_starved = 0
    for f in frames:
        pump._push_frame(f)

    with open(OUT_FILE, "wb"):
        pass

    r, w = os.pipe()
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "mjpeg", "-i", "pipe:", "-c:v", "copy", "-f", "mjpeg", OUT_FILE,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=r)
    pump.serve(w)
    deadline = time.time() + 20
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    try:
        proc.kill()
    except Exception:
        pass
    pump.stop()
    os.close(r)
    os.close(w)

    with open(OUT_FILE, "rb") as fh:
        data = fh.read()
    assert data.count(b"\xff\xd9") >= 45, "pacer must deliver (nearly) all frames"
    print(
        "test_pipeline_e2e: ALL PASS (%d frames, %d bytes)"
        % (data.count(b"\xff\xd9"), len(data))
    )


if __name__ == "__main__":
    main()
