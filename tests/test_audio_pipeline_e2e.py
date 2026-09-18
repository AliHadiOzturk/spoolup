import sys, os, time, subprocess, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OUT = "/tmp/opencode/_audio_e2e.wav"


def main():
    from spoolup.audio_server import AudioServer, SilenceSource, CHUNK_BYTES

    class SineSource:
        name = "sine"

        def __init__(self):
            self._phase = 0

        def read_chunk(self, n_bytes):
            import array, math
            n = n_bytes // 2
            out = array.array("h")
            for i in range(n):
                self._phase += 1
                out.append(int(8000 * math.sin(self._phase / 8.0)))
            return out.tobytes()

        def close(self):
            pass

    srv = AudioServer(volume=1.0)
    port = srv.start()
    srv.set_source(SineSource())

    proc = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "s16le", "-ar", "44100", "-ac", "2",
        "-i", "tcp://127.0.0.1:%d" % port,
        "-t", "3", "-f", "wav", OUT,
    ])
    rc = proc.wait(timeout=20)
    srv.stop()

    assert rc == 0, "ffmpeg consumer must exit 0"
    with open(OUT, "rb") as f:
        raw = f.read()
    assert len(raw) > 100_000, "3s of stereo 44.1kHz PCM expected"
    body = raw[44:]
    assert any(b != 0 for b in body), "audio must be non-silent (sine source)"


if __name__ == "__main__":
    main()
    print("test_audio_pipeline_e2e: ALL PASS")
