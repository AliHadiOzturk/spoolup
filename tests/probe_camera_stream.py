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
        boundary_markers: list = []
        chunks_list: list = []
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            if start is None:
                start = time.time()
            bytes_total += len(chunk)
            soi += chunk.count(b"\xff\xd8")
            eoi += chunk.count(b"\xff\xd9")
            chunks_list.append(chunk)
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
                marker += sum(c.count(b"--" + boundary) for c in chunks_list)
                print(f"boundary markers: {marker}")
            print(
                f"parser frames: {frames_total} "
                f"({frames_total/10:.1f}/s), avg size "
                f"{(sizes_total/max(1, frames_total))/1024:.0f} KB"
            )
            break

        # Offline classification of the SAME bytes: why are parts rejected?
        if boundary:
            full = b"".join(chunks_list)
            parts = full.split(b"--" + boundary)
            parts = parts[1:]  # leading empty segment
            cat = {"ok": 0, "no_header_end": 0, "not_soi": 0, "not_eoi": 0}
            rejects = []
            for part in parts:
                if part.endswith(b"--\r\n"):
                    continue  # terminal boundary
                head_end = part.find(b"\r\n\r\n")
                if head_end == -1:
                    cat["no_header_end"] += 1
                    rejects.append(("no_header_end", part[:80]))
                    continue
                payload = part[head_end + 4:].strip(b"\r\n")
                if not payload.startswith(b"\xff\xd8"):
                    cat["not_soi"] += 1
                    if len(rejects) < 3:
                        rejects.append(("not_soi", payload[:60]))
                    continue
                if not payload.endswith(b"\xff\xd9"):
                    cat["not_eoi"] += 1
                    if len(rejects) < 3:
                        rejects.append(("not_eoi", payload[-60:]))
                    continue
                cat["ok"] += 1
            print("--- offline split classification ---")
            print(cat)
            for kind, sample in rejects:
                print(f"reject[{kind}]: {sample!r}")


if __name__ == "__main__":
    main()
