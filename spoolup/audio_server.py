"""Live PCM audio server for the streaming pipeline.

Owns a localhost TCP listener that ffmpeg consumes as its audio input
(-f s16le -ar 44100 -ac 2 -i tcp://127.0.0.1:PORT — the server listens,
ffmpeg connects). Sources are swapped server-side with a short crossfade,
so music can change without restarting the stream. When this server is
unavailable, main.py falls back to the silent anullsrc input.
"""

import logging
import os
import shutil
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
SPOTIFY_DEVICE_NAME = "SpoolUp"
# Fixed Connect/HTTP advertise port so Windows Firewall rules are predictable.
# (mDNS itself still uses UDP 5353.)
SPOTIFY_ZEROCONF_PORT = 24879


def silence_chunk(n: int = CHUNK_BYTES) -> bytes:
    return b"\x00" * n


def resolve_librespot_path(configured: str = "") -> Optional[str]:
    """Return an executable librespot path, or None if unavailable.

    Accepts an absolute path, a bare command name on PATH, or falls back to
    discovering ``librespot`` on PATH when ``configured`` is empty.
    """
    path = (configured or "").strip()
    if path:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
        found = shutil.which(path)
        if found:
            return found
        return None
    return shutil.which("librespot")


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

    def alive(self) -> bool:
        return True

    def last_error(self) -> str:
        return ""


class SilenceSource(AudioSource):
    name = "silence"

    def read_chunk(self, n_bytes: int) -> bytes:
        return silence_chunk(n_bytes)


class _ProcessSource(AudioSource):
    """Base for sources backed by a subprocess writing s16le to stdout.

    By default the reader applies *backpressure*: when the queue is full it
    blocks instead of dropping. That keeps realtime producers (librespot)
    playing at 1x. File/ffmpeg sources can opt into drop-oldest buffering.
    """

    name = "process"
    # ~100 ms of PCM. Small on purpose so librespot cannot race ahead.
    _max_queue = 10
    _drop_when_full = False

    def __init__(self):
        self._proc = None
        self._thread = None
        self._err_thread = None
        self._lock = threading.Lock()
        self._queue = []
        self._closed = False
        self._eof = False
        self._stderr_lines = []  # type: List[str]
        self._have_pcm = False

    def _start(self, cmd, capture_stderr=False):
        import subprocess

        stderr = subprocess.PIPE if capture_stderr else subprocess.DEVNULL
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=stderr
        )
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        if capture_stderr and self._proc.stderr is not None:
            self._err_thread = threading.Thread(
                target=self._stderr_reader, daemon=True
            )
            self._err_thread.start()

    def _reader(self):
        try:
            while not self._closed and self._proc and self._proc.stdout:
                try:
                    data = self._proc.stdout.read(CHUNK_BYTES)
                except Exception:
                    break
                if not data:
                    break
                if any(b != 0 for b in data):
                    self._have_pcm = True
                while not self._closed:
                    with self._lock:
                        if len(self._queue) < self._max_queue:
                            self._queue.append(data)
                            break
                        if self._drop_when_full:
                            self._queue.pop(0)
                            self._queue.append(data)
                            break
                    # Backpressure: wait for AudioServer to consume.
                    time.sleep(CHUNK_MS / 1000.0)
        finally:
            self._eof = True

    def _stderr_reader(self):
        try:
            while not self._closed and self._proc and self._proc.stderr:
                try:
                    line = self._proc.stderr.readline()
                except Exception:
                    break
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                with self._lock:
                    self._stderr_lines.append(text)
                    del self._stderr_lines[: max(0, len(self._stderr_lines) - 40)]
                low = text.lower()
                if any(k in low for k in (
                    "error", "warn", "zeroconf", "discovery", "connect",
                    "listening", "mdns", "country",
                )):
                    logger.info("%s: %s", self.name, text)
                else:
                    logger.debug("%s stderr: %s", self.name, text)
        except Exception as e:
            logger.debug("%s stderr reader stopped: %s", self.name, e)

    def exhausted(self) -> bool:
        return self._eof and not self._queue

    def alive(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def last_error(self) -> str:
        with self._lock:
            if not self._stderr_lines:
                return ""
            return self._stderr_lines[-1]

    def wait_until_ready(self, timeout: float = 1.0) -> bool:
        """Return True if the process is still alive after a short settle."""
        deadline = time.time() + max(0.0, float(timeout))
        while time.time() < deadline:
            if not self.alive():
                self._eof = True
                return False
            time.sleep(0.05)
        if not self.alive():
            self._eof = True
            return False
        return True

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

    # ffmpeg can outrun the pacer; drop-oldest avoids unbounded RAM.
    _max_queue = 200
    _drop_when_full = True

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

    Important: the reader must *not* drain stdout faster than realtime.
    Doing so makes librespot finish tracks almost instantly and Spotify
    skips to the next song. Backpressure from ``_ProcessSource`` + a
    always-on AudioServer pacer keeps playback at 1x.
    """

    # Keep only ~100 ms buffered; block librespot when full.
    _max_queue = 10
    _drop_when_full = False

    @staticmethod
    def build_cmd(librespot_path: str, username: str = "", password: str = "",
                  device_name: str = SPOTIFY_DEVICE_NAME, cache_dir: str = "",
                  argv_override=None, zeroconf_port: int = SPOTIFY_ZEROCONF_PORT):
        """Build librespot argv for Spotify Connect (zeroconf) mode.

        ``username`` / ``password`` are ignored: Spotify removed password
        login, and modern librespot exits with an error if ``-p`` is passed.
        Login happens when the user picks this device in the Spotify app;
        credentials are cached under ``cache_dir``.
        """
        if argv_override:
            return [librespot_path] + list(argv_override)
        if password:
            logger.warning(
                "Ignoring spotify password — librespot password auth is gone; "
                "using Spotify Connect"
            )
        cmd = [
            librespot_path,
            "--name", device_name,
            "--backend", "pipe",
            "--format", "S16",
            "--bitrate", "160",
            "--initial-volume", "100",
            "--disable-audio-cache",
            "--device-type", "speaker",
        ]
        try:
            port = int(zeroconf_port or 0)
        except (TypeError, ValueError):
            port = 0
        if port > 1024:
            cmd += ["--zeroconf-port", str(port)]
        if cache_dir:
            # Credentials land in system-cache; --cache alone is enough on
            # older builds, but both keep modern librespot happy.
            cmd += ["--cache", cache_dir, "--system-cache", cache_dir]
        return cmd

    def __init__(self, librespot_path: str,
                 username: str = "", password: str = "",
                 device_name: str = SPOTIFY_DEVICE_NAME,
                 cache_dir: str = "", argv_override=None,
                 zeroconf_port: int = SPOTIFY_ZEROCONF_PORT):
        """Run librespot as a Spotify Connect receiver (zeroconf).

        No username/password are passed — pick the ``device_name`` device in
        the Spotify app; login is cached in ``cache_dir`` for later sessions.
        """
        super().__init__()
        self._eof = False
        self.name = "spotify"
        self.zeroconf_port = int(zeroconf_port or SPOTIFY_ZEROCONF_PORT)
        cmd = self.build_cmd(
            librespot_path, username, password,
            device_name, cache_dir, argv_override,
            zeroconf_port=self.zeroconf_port,
        )
        logger.info(
            "Starting librespot Connect receiver %r (zeroconf port %d)",
            device_name, self.zeroconf_port,
        )
        try:
            self._start(cmd, capture_stderr=True)
        except FileNotFoundError:
            logger.error("librespot not found: %s", librespot_path)
            self._proc = None
            self._eof = True
        except Exception as e:
            logger.error("librespot failed to start: %s", e)
            self._proc = None
            self._eof = True

    def exhausted(self) -> bool:
        if not self.alive() and not self._queue:
            self._eof = True
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
    """Realtime PCM pacer over a localhost TCP listener.

    Always drains the current source at realtime — even when ffmpeg is not
    connected — so Spotify Connect (librespot pipe) keeps correct timing
    instead of racing through tracks and skipping.
    """

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
        self._chunks_sent = 0
        self._chunks_drained = 0

    # ---- lifecycle ----
    def start(self) -> int:
        if self._listener is not None:
            return self._port
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind(("127.0.0.1", 0))
        lsock.listen(1)
        lsock.settimeout(0.0)  # non-blocking accept; pacer always runs
        self._listener = lsock
        self._port = lsock.getsockname()[1]
        self._thread = threading.Thread(
            target=self._pace_loop, daemon=True
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
            source = self._source
            alive = True
            err = ""
            have_pcm = False
            try:
                alive = bool(source.alive())
            except Exception:
                alive = False
            try:
                err = source.last_error() or ""
            except Exception:
                err = ""
            try:
                have_pcm = bool(getattr(source, "_have_pcm", False))
            except Exception:
                have_pcm = False
            return {
                "port": self._port,
                "source": source.name,
                "source_alive": alive,
                "source_error": err,
                "receiving_pcm": have_pcm,
                "volume": self._volume,
                "listening": self._listener is not None,
                "client_connected": self._conn is not None,
                "fading": self._fade_left > 0,
                "chunks_drained": self._chunks_drained,
                "chunks_sent": self._chunks_sent,
            }

    # ---- internals ----
    def _try_accept(self) -> None:
        if self._listener is None or self._conn is not None:
            return
        try:
            conn, _ = self._listener.accept()
            conn.settimeout(None)
            self._conn = conn
            logger.info("AudioServer: ffmpeg connected")
        except BlockingIOError:
            return
        except socket.timeout:
            return
        except OSError as e:
            if not self._stop.is_set():
                logger.debug("AudioServer accept: %s", e)

    def _next_chunk(self) -> bytes:
        with self._lock:
            cur = self._source
            old = self._fade_from
            fading = self._fade_left
            volume = self._volume
        chunk = cur.read_chunk(CHUNK_BYTES)
        if old is not None and fading > 0:
            t = 1.0 - (fading / float(FADE_CHUNKS))
            chunk = mix_pcm(old.read_chunk(CHUNK_BYTES), chunk, t)
            with self._lock:
                self._fade_left -= 1
                if self._fade_left <= 0:
                    old.close()
                    self._fade_from = None
        return scale_pcm(chunk, volume)

    def _pace_loop(self):
        """Always drain the source at realtime; fan out to ffmpeg when present."""
        interval = CHUNK_MS / 1000.0
        next_tick = time.time()
        while not self._stop.is_set():
            self._try_accept()
            wait = next_tick - time.time()
            if wait > 0:
                self._stop.wait(wait)
                if self._stop.is_set():
                    break
            chunk = self._next_chunk()
            self._chunks_drained += 1
            conn = self._conn
            if conn is not None:
                try:
                    conn.sendall(chunk)
                    self._chunks_sent += 1
                except OSError as e:
                    logger.error("AudioServer write failed: %s", e)
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self._conn = None
            next_tick += interval
            if next_tick < time.time() - 1.0:
                next_tick = time.time()  # never burst-catch-up
