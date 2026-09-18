"""Buffered frame pump between the MJPEG webcam and ffmpeg.

The K1 webcam deterministically stalls (multi-second pauses). Feeding
ffmpeg directly from HTTP channels those stalls into the RTMP output as
videoIngestionStarved + progressive lag. FramePump (Task 2) decouples the
two halves: reader thread fills a bounded ring buffer, pacer thread
writes frames to ffmpeg at 1/fps.
"""

import logging
import threading
import time
import os
from collections import deque
from typing import Callable, List, Optional

import requests

logger = logging.getLogger(__name__)

_SOI = b"\xff\xd8"  # JPEG Start Of Image
_EOI = b"\xff\xd9"  # JPEG End Of Image


class MjpegFrameParser:
    """Incremental multipart/x-mixed-replace MJPEG parser.

    Feed arbitrary byte chunks; get complete JPEG frames back.
    If `boundary` is None, falls back to a raw SOI/EOI scan.
    """

    MAX_STALE_BUFFER = 4 * 1024 * 1024  # bytes; drop runaway garbage buffers

    def __init__(self, boundary: Optional[bytes] = None):
        self._marker: Optional[bytes] = b"--" + boundary if boundary else None
        self._buf = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        self._buf.extend(data)
        if self._marker is not None:
            frames = self._drain_multipart()
        else:
            frames = self._drain_soiful()
        if not frames and len(self._buf) > self.MAX_STALE_BUFFER:
            self._buf = bytearray()  # runaway garbage buffer guard
        return frames

    def _drain_multipart(self) -> List[bytes]:
        assert self._marker is not None
        frames: List[bytes] = []
        parts = self._buf.split(self._marker)
        self._buf = bytearray(parts.pop())  # last part may be incomplete
        for part in parts:
            head_end = part.find(b"\r\n\r\n")
            if head_end == -1:
                continue
            payload = part[head_end + 4:]
            # Some servers zero-pad frames to a multiple of N: trim the
            # trailing CRLF and any padding so the payload ends at EOI.
            while payload and payload[-1:] in (b"\r", b"\n", b"\x00"):
                payload = payload[:-1]
            if payload.startswith(_SOI) and payload.endswith(_EOI):
                frames.append(payload)
        return frames

    def _drain_soiful(self) -> List[bytes]:
        frames: List[bytes] = []
        while True:
            soi = self._buf.find(_SOI)
            if soi == -1:
                # No frame possible; keep last byte in case SOI is split
                if len(self._buf) > 1:
                    self._buf = bytearray(self._buf[-1:])
                break
            if soi > 0:
                self._buf = self._buf[soi:]
            eoi = self._buf.find(_EOI, 2)
            if eoi == -1:
                if len(self._buf) > self.MAX_STALE_BUFFER:
                    self._buf = bytearray()  # runaway buffer (junk SOI)
                break
            end = eoi + len(_EOI)
            frames.append(bytes(self._buf[:end]))
            self._buf = self._buf[end:]
        return frames


def parse_boundary(content_type: str) -> Optional[bytes]:
    if not content_type:
        return None
    for field in content_type.split(";"):
        field = field.strip()
        if field.lower().startswith("boundary="):
            value = field.split("=", 1)[1].strip().strip('"')
            if value:
                return value.encode("ascii", "replace")
    return None


class FramePump:
    """Decouples a bursty MJPEG HTTP source from ffmpeg's stdin.

    reader thread → parse frames → bounded ring buffer (drop-oldest)
    pacer thread  → pop at 1/fps → os.write(pipe_fd) (repeat-last on empty)
    """

    def __init__(self, webcam_url: str, fps: int, buffer_seconds: int = 10):
        self.webcam_url = webcam_url
        self.fps = max(1, int(fps))
        self._interval = 1.0 / self.fps
        capacity = max(1, self.fps * max(1, int(buffer_seconds)))
        self._buffer: deque = deque(maxlen=capacity)
        self._last: Optional[bytes] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._pacer_thread: Optional[threading.Thread] = None
        self._response = None
        # 10s-interval diagnostics (frames in/out, drops, buffer depth)
        self._stats_frames_read = 0
        self._stats_bytes_read = 0
        self._stats_frames_stale_dropped = 0  # overwritten by deque overflow
        self._stats_frames_paced = 0
        self._stats_frames_starved = 0  # pacer ticks with nothing new (dup)
        self._stats_lock = threading.Lock()
        # Last computed 10s stats snapshot (read by watchdog/dashboard)
        self.last_stats: Optional[dict] = None

    def start(self) -> None:
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

    def wait_for_first_frame(self, timeout: float = 10.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if len(self._buffer) > 0:
                    return True
            self._stop.wait(0.2)
        logger.error(
            "FramePump: no frame within %.1fs from %s", timeout, self.webcam_url
        )
        return False

    def serve(self, pipe_fd) -> None:
        self._pacer_thread = threading.Thread(
            target=self._pacer_loop, args=(pipe_fd,), daemon=True
        )
        self._pacer_thread.start()
        self._start_stats_loop()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._response is not None:
                self._response.close()
        except Exception:
            pass
        for t in (self._pacer_thread, self._reader_thread):
            if t and t.is_alive():
                t.join(timeout=5)

    # ---- diagnostics ---------------------------------------------------
    def _start_stats_loop(self) -> None:
        def stats_loop():
            prev_in = prev_out = 0
            while not self._stop.wait(10.0):
                with self._stats_lock:
                    read = self._stats_frames_read
                    bytes_read = self._stats_bytes_read
                    paced = self._stats_frames_paced
                    stale = self._stats_frames_stale_dropped
                    starved = self._stats_frames_starved
                logger.info(
                    "FramePump stats 10s: read=%d (%.1f/s, %.1f KB/s) "
                    "paced=%d (%.1f/s) buffer=%d stale_drop=%.1f/s "
                    "dup_ticks=%.1f/s",
                    read - prev_in, (read - prev_in) / 10.0,
                    bytes_read / 10240.0,
                    paced - prev_out, (paced - prev_out) / 10.0,
                    len(self._buffer), stale / 10.0, starved / 10.0,
                )
                self.last_stats = {
                    "read_rate": (read - prev_in) / 10.0,
                    "paced_rate": (paced - prev_out) / 10.0,
                    "buffer": len(self._buffer),
                    "dup_rate": starved / 10.0,
                    "stale_drop_rate": stale / 10.0,
                    "ts": time.time(),
                }
                prev_in, prev_out = read, paced

        threading.Thread(target=stats_loop, daemon=True).start()

    # ---- internals (also unit-test entry points) ----------------------
    def _push_frame(self, frame: bytes) -> None:
        with self._lock:
            if self._buffer.maxlen and len(self._buffer) >= self._buffer.maxlen:
                with self._stats_lock:
                    self._stats_frames_stale_dropped += 1
            self._buffer.append(frame)  # deque maxlen drops-oldest
            self._last = frame
        with self._stats_lock:
            self._stats_frames_read += 1

    def _next_frame(self):
        """Pop the next frame; returns (frame_or_None, was_fresh)."""
        with self._lock:
            if self._buffer:
                self._last = self._buffer.popleft()
                return self._last, True
            return self._last, False

    def _reader_loop(self) -> None:
        backoff = 1.0
        resp = None
        while not self._stop.is_set():
            try:
                resp = requests.get(
                    self.webcam_url, stream=True, timeout=(5, 60)
                )
                if resp.status_code != 200:
                    raise RuntimeError("webcam HTTP %s" % resp.status_code)
                with self._lock:
                    self._response = resp
                ctype = resp.headers.get("content-type", "")
                parser = MjpegFrameParser(parse_boundary(ctype))
                backoff = 1.0
                logger.debug("FramePump connected to %s", self.webcam_url)
                gen = resp.iter_content(chunk_size=8192)
                while not self._stop.is_set():
                    chunk = next(gen)
                    if not chunk:
                        continue
                    with self._stats_lock:
                        self._stats_bytes_read += len(chunk)
                    for frame in parser.feed(chunk):
                        self._push_frame(frame)
            except StopIteration:
                logger.warning("FramePump: webcam stream ended; reconnecting")
            except Exception as exc:
                logger.warning("FramePump: %s; retry in %.0fs", exc, backoff)
            finally:
                with self._lock:
                    self._response = None
                try:
                    if resp is not None:
                        resp.close()
                except Exception:
                    pass
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 30)

    def _pacer_loop(self, pipe_fd) -> None:
        next_tick = time.time()
        while not self._stop.is_set():
            wait = next_tick - time.time()
            if wait > 0:
                self._stop.wait(wait)
                if self._stop.is_set():
                    break
            frame, fresh = self._next_frame()
            if frame is None:
                next_tick = time.time() + self._interval
                continue
            with self._stats_lock:
                self._stats_frames_paced += 1
                if not fresh:
                    self._stats_frames_starved += 1
            try:
                os.write(pipe_fd, frame)
            except (BrokenPipeError, OSError):
                break
            next_tick += self._interval
            if next_tick < time.time() - 1.0:
                next_tick = time.time()  # never burst-catch-up after lag
