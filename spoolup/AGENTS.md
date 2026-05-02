# SPOOLUP RUNTIME KNOWLEDGE BASE

**Scope:** Printer-side streaming daemon (runs on embedded Linux)

## OVERVIEW
Monolithic Python runtime that connects to Moonraker (Klipper), streams webcam MJPEG via FFmpeg to YouTube Live RTMP, and uploads timelapse videos on print completion.

## STRUCTURE

```
spoolup/
├── __init__.py    # Exports main()
├── __main__.py    # python -m spoolup entry point
└── main.py        # 1940-line monolith (all runtime logic)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Config loading | `main.py:Config` class | JSON with DEFAULTS dict |
| Moonraker WS | `main.py:MoonrakerClient` | WebSocketApp callbacks + REST |
| Stream control | `main.py:YouTubeStreamer` | FFmpeg subprocess mgmt |
| State machine | `main.py` | print_state → stream actions |
| Timelapse upload | `main.py` | Finds newest .mp4 in timelapse dir |
| Health check | `main.py` | YouTube API stream health poll |

## CONVENTIONS (Runtime)

- Hardware encoding: `-c:v h264_qsv` (Intel QuickSync) is default
- Silent audio track required: `-f lavfi -i anullsrc`
- MJPEG input → RTMP output (never change this architecture)
- FFmpeg filter_complex for rescaling/overlay
- Token loaded from `youtube_token.json` (no OAuth on printer)
- WebSocket reconnection with exponential backoff

## ANTI-PATTERNS

- Do NOT add OAuth libs to this package — use pre-generated token
- Do NOT remove hardware encoding unless testing fallback
- Do NOT change filter_complex structure
- Do NOT break config backward compatibility

## NOTES

- **Error state = transient**: Stream continues during Klipper errors
- Stream stops only on `complete` or `cancelled` states
- FFmpeg process monitored via subprocess + periodic health checks
- Config path: `-c /path/to/config.json` (required)
- Target: Creality K1/K2/Sonic Pad (OpenWrt/Buildroot) or generic Linux
