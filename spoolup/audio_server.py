"""Live PCM audio server for the streaming pipeline.

Owns a localhost TCP listener that ffmpeg consumes as its audio input
(-f s16le -ar 44100 -ac 2 -i tcp://127.0.0.1:PORT — the server listens,
ffmpeg connects). Sources are swapped server-side with a short crossfade,
so music can change without restarting the stream. When this server is
unavailable, main.py falls back to the silent anullsrc input.
"""

import logging
import os
import socket
import threading
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 2
BYTES_PER_SAMPLE = 2
CHUNK_MS = 10
CHUNK_BYTES = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE * CHUNK_MS // 1000
FADE_CHUNKS = 50  # 500 ms crossfade


def silence_chunk(n: int = CHUNK_BYTES) -> bytes:
    return b"\x00" * n


def scale_pcm(data: bytes, volume: float) -> bytes:
    """Apply int16 volume scaling; volume clamped to [0.0, 1.5]."""
    v = max(0.0, min(1.5, float(volume)))
    if v == 1.0 or not data:
        return data
    import array

    samples = array.array("h")
    samples.frombytes(data[: len(data) - (len(data) % 2)])
    clipped = array.array("h", (
        max(-32768, min(32767, int(s * v))) for s in samples
    ))
    return clipped.tobytes() + data[len(clipped.tobytes()):]


def mix_pcm(a: bytes, b: bytes, t: float) -> bytes:
    """Linear crossfade: a*(1-t) + b*t, t in [0,1]."""
    import array

    n = min(len(a), len(b))
    n -= n % 2
    if n <= 0:
        return b if t >= 1.0 else a
    sa = array.array("h")
    sa.frombytes(a[:n])
    sb = array.array("h")
    sb.frombytes(b[:n])
    out = array.array("h", (
        max(-32768, min(32767, int(sa[i] * (1.0 - t) + sb[i] * t)))
        for i in range(len(sa))
    ))
    return out.tobytes()


class AudioSource:
    """Duck-typed PCM producer: s16le stereo 44.1 kHz."""

    name = "unknown"

    def read_chunk(self, n_bytes: int) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SilenceSource(AudioSource):
    name = "silence"

    def read_chunk(self, n_bytes: int) -> bytes:
        return silence_chunk(n_bytes)


class _ProcessSource(AudioSource):
    """Base for sources backed by a subprocess writing s16le to stdout."""

    name = "process"

    def __init__(self):
        self._proc = None
        self._thread = None
        self._lock = threading.Lock()
        self._queue = []
        self._closed = False
        self._eof = False

    def _start(self, cmd):
        import subprocess

        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        try:
            while not self._closed and self._proc and self._proc.stdout:
                try:
                    data = self._proc.stdout.read(CHUNK_BYTES)
                except Exception:
                    break
                if not data:
                    break
                with self._lock:
                    self._queue.append(data)
        finally:
            self._eof = True

    def exhausted(self) -> bool:
        return self._eof and not self._queue

    def read_chunk(self, n_bytes: int) -> bytes:
        with self._lock:
            if self._queue:
                data = self._queue.pop(0)
                if len(data) >= n_bytes:
                    return data[:n_bytes]
                return data + silence_chunk(n_bytes - len(data))
        return silence_chunk(n_bytes)

    def close(self) -> None:
        self._closed = True
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


class FileSource(_ProcessSource):
    """Loops a single audio file through ffmpeg as s16le PCM."""

    def __init__(self, path: str):
        super().__init__()
        self._eof = False
        self.name = "file:%s" % os.path.basename(path)
        try:
            self._start([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-stream_loop", "-1", "-i", path,
                "-f", "s16le", "-ac", "2", "-ar", "44100", "-",
            ])
        except Exception as e:
            logger.error("FileSource could not start (%s): %s", path, e)
            self._proc = None
            self._eof = True


class LibrespotSource(_ProcessSource):
    """Spotify audio via librespot's pipe backend (s16le on stdout).

    Playback is controlled through Spotify Connect: the user casts to the
    ``device_name`` device from their Spotify app. Volume is applied by the
    AudioServer. ``argv_override`` is a test hook: when given, the spawn
    command is ``[librespot_path, *argv_override]`` instead of the real
    librespot arguments.
    """

    @staticmethod
    def build_cmd(librespot_path: str, username: str, password: str,
                  device_name: str = "SpoolUp", cache_dir: str = "",
                  argv_override=None):
        if argv_override:
            return [librespot_path] + list(argv_override)
        cmd = [
            librespot_path,
            "--name", device_name,
            "--backend", "pipe",
        ]
        if username and password:
            cmd += ["--username", username, "--password", password]
        elif cache_dir:
            cmd += ["--cache", cache_dir]
        return cmd

    def __init__(self, librespot_path: str,
                 username: str = "", password: str = "",
                 device_name: str = "SpoolUp",
                 cache_dir: str = "", argv_override=None):
        """Modern Spotify accounts log in via the app's verification code,
        so by default the source runs in ZEROCONF (Spotify Connect) mode:
        no credentials are passed, the user selects the device in their
        Spotify app, and the login is cached in ``cache_dir`` for later
        sessions. If BOTH username and password are given (legacy librespot
        builds that still support password auth), they are used instead."""
        super().__init__()
        self._eof = False
        self.name = "spotify"
        cmd = self.build_cmd(librespot_path, username, password,
                             device_name, cache_dir, argv_override)
        try:
            self._start(cmd)
        except FileNotFoundError:
            logger.error("librespot not found: %s", librespot_path)
            self._proc = None
            self._eof = True
        except Exception as e:
            logger.error("librespot failed to start: %s", e)
            self._proc = None
            self._eof = True

    def exhausted(self) -> bool:
        return self._eof and not self._queue


class PlaylistSource(AudioSource):
    name = "playlist"

    def __init__(self, paths: List[str], loop: bool = True):
        self._paths = list(paths)
        self._loop = loop
        self._idx = 0
        self._current: Optional[FileSource] = None
        self._lock = threading.Lock()
        self._make = FileSource  # overridable in tests

    def _ensure_current(self) -> None:
        passes = 0
        while passes < len(self._paths) * 2:
            passes += 1
            if self._current is None:
                if not self._paths:
                    return
                if self._idx >= len(self._paths):
                    if not self._loop:
                        return
                    self._idx = 0
                self._current = self._make(self._paths[self._idx])
            if self._current.exhausted():
                self._current.close()
                self._current = None
                self._idx += 1
                continue
            return
        self._current = None

    def read_chunk(self, n_bytes: int) -> bytes:
        with self._lock:
            self._ensure_current()
            if self._current is None:
                return silence_chunk(n_bytes)
            return self._current.read_chunk(n_bytes)

    def close(self) -> None:
        with self._lock:
            if self._current is not None:
                self._current.close()
                self._current = None


class AudioServer:
    """Realtime PCM pacer over a localhost TCP listener."""

    def __init__(self, volume: float = 0.8):
        self._volume = max(0.0, min(1.5, float(volume)))
        self._listener: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None
        self._port = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._source: AudioSource = SilenceSource()
        self._fade_from: Optional[AudioSource] = None
        self._fade_left = 0
        self._lock = threading.Lock()

    # ---- lifecycle ----
    def start(self) -> int:
        if self._listener is not None:
            return self._port
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind(("127.0.0.1", 0))
        lsock.listen(1)
        lsock.settimeout(30)
        self._listener = lsock
        self._port = lsock.getsockname()[1]
        self._thread = threading.Thread(
            target=self._accept_and_pace, daemon=True
        )
        self._thread.start()
        logger.info("AudioServer listening on 127.0.0.1:%d", self._port)
        return self._port

    @property
    def port(self) -> int:
        return self._port

    def stop(self) -> None:
        self._stop.set()
        for sock in (self._conn, self._listener):
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
        self._conn = None
        self._listener = None
        with self._lock:
            self._source.close()
            if self._fade_from is not None:
                self._fade_from.close()
                self._fade_from = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    # ---- control ----
    def set_source(self, source: AudioSource) -> None:
        with self._lock:
            if self._fade_from is not None:
                self._fade_from.close()
            self._fade_from = self._source
            self._source = source
            self._fade_left = FADE_CHUNKS
        logger.info("AudioServer source -> %s", source.name)

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.5, float(volume)))

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "port": self._port,
                "source": self._source.name,
                "volume": self._volume,
                "listening": self._listener is not None,
                "client_connected": self._conn is not None,
                "fading": self._fade_left > 0,
            }

    # ---- internals ----
    def _accept_and_pace(self):
        interval = CHUNK_MS / 1000.0
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
                conn.settimeout(None)
                self._conn = conn
                logger.info("AudioServer: ffmpeg connected")
            except socket.timeout:
                continue
            except OSError as e:
                if self._stop.is_set():
                    break
                logger.error("AudioServer accept failed: %s", e)
                break
            next_tick = time.time()
            while not self._stop.is_set():
                wait = next_tick - time.time()
                if wait > 0:
                    self._stop.wait(wait)
                    if self._stop.is_set():
                        break
                with self._lock:
                    cur = self._source
                    old = self._fade_from
                    fading = self._fade_left
                chunk = cur.read_chunk(CHUNK_BYTES)
                if old is not None and fading > 0:
                    t = 1.0 - (fading / float(FADE_CHUNKS))
                    chunk = mix_pcm(old.read_chunk(CHUNK_BYTES), chunk, t)
                    with self._lock:
                        self._fade_left -= 1
                        if self._fade_left <= 0:
                            old.close()
                            self._fade_from = None
                chunk = scale_pcm(chunk, self._volume)
                try:
                    conn.sendall(chunk)
                except OSError as e:
                    logger.error("AudioServer write failed: %s", e)
                    break
                next_tick += interval
                if next_tick < time.time() - 1.0:
                    next_tick = time.time()  # never burst-catch-up
            try:
                if self._conn is not None:
                    self._conn.close()
            except Exception:
                pass
            self._conn = None
