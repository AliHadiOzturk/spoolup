"""Helpers for building synthetic MJPEG multipart streams in tests."""
from typing import List

SOI = b"\xff\xd8\xff\xe0"
EOI = b"\xff\xd9"


def make_jpeg(frame_var: int = 0, payload_size: int = 64) -> bytes:
    """Structurally correct SOI...EOI byte string (not a decodable JPEG;
    only parser/pump logic is exercised, never encoding)."""
    body = bytes([frame_var % 256]) * payload_size
    return SOI + body + EOI


def make_multipart(frames: List[bytes], boundary: bytes) -> bytes:
    out = bytearray()
    for f in frames:
        out += b"--" + boundary + b"\r\n"
        out += b"Content-Type: image/jpeg\r\n\r\n"
        out += f + b"\r\n"
    out += b"--" + boundary + b"--\r\n"
    return bytes(out)


def chunked(data: bytes, sizes: List[int]) -> List[bytes]:
    out, pos, i = [], 0, 0
    while pos < len(data):
        out.append(data[pos:pos + sizes[i % len(sizes)]])
        pos += len(out[-1])
        i += 1
    return out
