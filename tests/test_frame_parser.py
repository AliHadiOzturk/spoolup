import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.mjpeg_util import make_jpeg, make_multipart, chunked
from spoolup.frame_pump import MjpegFrameParser


def test_parse_clean_stream():
    boundary = b"spoolupbound"
    frames = [make_jpeg(i) for i in range(5)]
    data = make_multipart(frames, boundary)
    p = MjpegFrameParser(boundary)
    got = []
    for chunk in chunked(data, [1, 7, 3, 109, 2]):
        got.extend(p.feed(chunk))
    assert got == frames


def test_parse_splits_chunks_arbitrarily():
    boundary = b"xyz"
    frames = [make_jpeg(i, payload_size=300) for i in range(3)]
    data = make_multipart(frames, boundary)
    got = []
    p = MjpegFrameParser(boundary)
    for chunk in chunked(data, [3]):
        got.extend(p.feed(chunk))
    assert got == frames


def test_parse_leading_garbage():
    boundary = b"xyz"
    frames = [make_jpeg(i) for i in range(2)]
    data = b"GARBAGE-JUNK" + make_multipart(frames, boundary)
    p = MjpegFrameParser(boundary)
    got = []
    for ch in chunked(data, [5]):
        got.extend(p.feed(ch))
    assert got == frames


def test_no_boundary_falls_back_to_soiful_scan():
    frames = [make_jpeg(i) for i in range(3)]
    data = make_multipart(frames, b"whatever") + frames[2]
    p = MjpegFrameParser(None)
    got = []
    for ch in chunked(data, [17]):
        got.extend(p.feed(ch))
    assert got == frames + [frames[2]]


if __name__ == "__main__":
    test_parse_clean_stream()
    test_parse_splits_chunks_arbitrarily()
    test_parse_leading_garbage()
    test_no_boundary_falls_back_to_soiful_scan()
    print("test_frame_parser: ALL PASS")
