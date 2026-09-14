"""Camera wire-format probe: run on the streaming machine.

    python tests/probe_camera_stream.py http://<printer_ip>:8080/?action=stream

Prints the Content-Type header, byte counts, boundary/JPEG marker counts,
and what our MjpegFrameParser manages to extract from the same bytes.
"""
import sys
import time

import requests

sys.path.insert(0, ".")
from spoolup.frame_pump import MjpegFrameParser, parse_boundary  # noqa: E402


def main() -> None:
    url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "http://localhost:8080/?action=stream"
    )
    print(f"Connecting: {url}")
    with requests.get(url, stream=True, timeout=(5, 60)) as resp:
        print(f"HTTP {resp.status_code}")
        for k, v in resp.headers.items():
            print(f"  {k}: {v}")
        ctype = resp.headers.get("content-type", "")
        boundary = parse_boundary(ctype)
        print(f"parsed boundary: {boundary!r}")

        parser = MjpegFrameParser(boundary)
        start = None
        bytes_total = 0
        soi = 0
        eoi = 0
        marker = 0
        frames_total = 0
        sizes_total = 0
        first_bytes_shot = False
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            if start is None:
                start = time.time()
            bytes_total += len(chunk)
            soi += chunk.count(b"\xff\xd8")
            eoi += chunk.count(b"\xff\xd9")
            if boundary:
                marker += chunk.count(b"--" + boundary)
            if not first_bytes_shot:
                print("first 300 bytes:", chunk[:300])
                first_bytes_shot = True
            frames = parser.feed(chunk)
            frames_total += len(frames)
            sizes_total += sum(len(f) for f in frames)
            elapsed = time.time() - start
            if elapsed < 10.0:
                continue
            print("--- 10s window ---")
            print(f"bytes received: {bytes_total} ({bytes_total/10/1024:.0f} KB/s)")
            print(f"SOI markers: {soi}  EOI markers: {eoi}")
            if boundary:
                print(f"boundary markers: {marker}")
            print(
                f"parser frames: {frames_total} "
                f"({frames_total/10:.1f}/s), avg size "
                f"{(sizes_total/max(1, frames_total))/1024:.0f} KB"
            )
            break


if __name__ == "__main__":
    main()
