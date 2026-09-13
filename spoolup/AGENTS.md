# spoolup runtime knowledge base

**Scope** Streaming-machine runtime (PC/Mac/Linux; NOT the printer — printer SoCs cannot sustain live encoding)

## overview
Monolith Python runtime that connects to Moonraker (Klipper) over the network, streams a buffered webcam MJPEG via a single FFmpeg `tee` to YouTube Live RTMP AND Kick (rtmp/srt), and uploads timelapse videos on print completion.

## structure

```
spoolup/
├── __init__.py    # Exports main()
├── __main__.py    # python -m spoolup entry point
├── frame_pump.py  # Buffered MJPEG reader/pacer (webcam → ffmpeg stdin pipe)
└── main.py        # ~2200-line monolith (StreamManager, config, moonraker, uploader)
```

## where to look

| Task | Location | Notes |
|------|----------|-------|
| Config loading | `main.py:Config` | JSON with DEFAULTS dict |
| Moonraker WS | `main.py:MoonrakerClient` | WebSocketApp callbacks + REST |
| Stream control | `main.py:StreamManager` | ffmpeg tee pipeline mgmt |
| Output fan-out | `main.py:StreamManager._build_output_spec` | tee spec; flv for rtmp, mpegts for srt |
| Webcam ingest | `frame_pump.py:FramePump` | reader thread + ring buffer + pacer |
| Kick sink | `main.py:StreamManager` | kick_enabled/kick_rtmp_url/kick_stream_key |
| Key masking | `main.py:_masked_text/_log_ffmpeg_command` | never log stream keys |
| State machine | `main.py` | print state → stream actions |
| Timelapse upload | `main.py:YouTubeUploader` | newest match in `timelapse_dir` |
| Health check | `main.py` | YouTube API stream health poll |

## conventions (runtime)

- One ffmpeg process; `tee` muxer handles multi-destination (`[f=flv:onfail=ignore]...|[f=flv:onfail=ignore]...`)
- MJPEG frames come from `frame_pump` stdin pipe, NOT HTTP (hack flags removed on purpose)
- Hardware encode default (`h264_qsv`), fallback `libx264`
- Silent audio track required: `-f lavfi -i anullsrc`
- Token loaded from `youtube_token.json` (no OAuth in the runtime)
- WebSocket reconnection with exponential backoff

## anti-patterns

- Do NOT add OAuth libs to this package — use pre-generated token
- Do NOT feed ffmpeg from HTTP directly — always through `frame_pump` (starvation bug history)
- Do NOT remove hardware encoding unless testing fallback
- Do NOT change the tee/filter_complex structure
- Do NOT break config backward compatibility
- Do NOT log stream keys (use `_mask_key`/`_masked_text`)

## notes

- **Error state = transient**: Stream continues during Klipper errors
- Stream stops only on `complete` or `cancelled` states
- Kick stream key + ingests are credentials — config.json must stay out of repos
- Config path: `-c /path/to/config.json` (required)
- Target: Windows/Linux/macOS streaming machines (QSV/NVENC/VideoToolbox detection); printers accessed over the network only
