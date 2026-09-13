# Design: Multi-Destination Streaming (YouTube + Kick) with Buffered Ingest

**Date:** 2026-09-12
**Status:** Approved (pending implementation plan)
**Scope:** Printer-side runtime (`spoolup/`)

## Problem

1. **YouTube buffering** — progressive lag plus periodic `videoIngestionStarved`
   health indicators. Root cause: the K1 webcam's MJPEG HTTP feed stalls
   deterministically (~9s pause around frame 308); ffmpeg drains its input queue
   in a burst and then starves. Existing mitigations (`thread_queue_size`,
   wallclock timestamps, CFR output pacing) only defer the failure.
2. **No Kick support** — the stream must also publish to Kick simultaneously.
   Kick has no public broadcast API; publishing means pushing RTMP to a static
   ingest URL + stream key from the Kick Creator dashboard.

## Goals

- Single ffmpeg process: one video encode, two RTMP outputs.
- Structurally eliminate ingestion starvation and progressive lag.
- Zero-output regression for YouTube-only configs (backward compatible).

## Non-Goals (YAGNI)

- Kick chat/status API consumption.
- Per-sink resolutions or bitrates (both sinks take the same encode).
- Any new config surface beyond the 4 keys below.

## Architecture

```
MJPEG webcam ──▶ FramePump (Python) ──▶ FFmpeg (single encode, tee muxer)
                 reader + ring buffer   ├─[f=flv:onfail=ignore]──▶ rtmp://YouTube  (+ API lifecycle)
                 + pacer → stdin pipe   └─[f=flv:onfail=ignore]──▶ rtmp://Kick    (+ static URL+key)
```

## Components

### 1. `spoolup/frame_pump.py` (new module)

- **Reader thread**: HTTP-streams the webcam MJPEG URL
  (`multipart/x-mixed-replace`), extracts frames, reconnects with exponential
  backoff on disconnect. Startup includes the existing HTTP connectivity test.
- **Ring buffer**: `deque(maxlen=fps * ingest_buffer_seconds)`.
  - Full → drop oldest (latency stays bounded).
  - Empty → repeat last frame so the encoder never starves.
- **Pacer thread**: writes frames to ffmpeg stdin at `1/fps` cadence.

### 2. ffmpeg command changes (`StreamManager._build_ffmpeg_cmd`)

- Input becomes `-f image2pipe -framerate <fps> -c:v mjpeg -` reading from a
  `os.pipe` backed by the pump.
- Removed hacks (compensated by the pump): `-thread_queue_size 2048`,
  `-use_wallclock_as_timestamps 1`, `-fflags +discardcorrupt`.
- Output: single `tee` muxer URL string built from enabled sinks:
  `[f=flv:onfail=ignore]<youtube_rtmp>|[f=flv:onfail=ignore]<kick_rtmp>`
- Everything else unchanged: encoder detection (`h264_qsv` → `libx264`
  fallback), GOP, CBR options, audio (`anullsrc` + aac), filter chain.

### 3. `YouTubeStreamer` → `StreamManager` (rename/extend in `main.py`)

- Builds the tee output string from enabled sinks.
- YouTube sink keeps all existing API lifecycle: broadcast creation,
  state transitions, health monitoring loop, description updates,
  `_restart_ffmpeg_stream` (now restarts pump + ffmpeg).
- Kick sink is passive: URL + key from config, no API calls.

## Configuration (config.json)

```json
{
  "kick_enabled": true,
  "kick_rtmp_url": "rtmp://fa723fc1b91d4.global-media-services.com:1935/live",
  "kick_stream_key": "<from Kick Creator dashboard>",
  "ingest_buffer_seconds": 10
}
```

- All keys optional; defaults keep YT-only behavior identical.
- `kick_stream_key` is sensitive: never logged in full, never committed.

## Error Handling

| Failure | Behavior |
|---|---|
| Pump reader dies | Backoff reconnect inside pump; after repeated failures surfaces via ffmpeg monitor → existing restart path |
| Kick RTMP unreachable | `tee onfail=ignore` drops only the Kick leg; YouTube unaffected; WARN logged |
| YouTube ingestion starvation | Existing health-monitor restart logic kept; expected rare with the pump |
| ffmpeg fails to start | Existing stderr capture + encoder-fallback path kept |

## Testing

- Pump logic directly unit-testable on dev machine: multipart parse,
  drop-oldest on overflow, repeat-last on underflow — synthetic MJPEG source
  (e.g. `ffmpeg` lavfi testsrc loop), no printer required.
- `python -m py_compile` + `test_setup.py`.
- Printer verification: one print with `kick_enabled` on; watch Kick dashboard
  and YouTube ingest health.

## Security Notes

- Kick stream key and RTMP URL stored in user-supplied `config.json`
  (outside the repository, same class as `youtube_token.json`).
- Mask stream key in all logs (first 4 chars max).
