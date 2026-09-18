# Design: SpoolUp Dashboard & 24/7 Streaming Management

**Date:** 2026-09-14 · **Status:** draft — brainstorm approved, awaiting user review (nothing implemented or committed)

## Problem

SpoolUp runs from a command line only; non-technical users cannot operate it. It is intended to run 24/7 unattended. Requirements collected:

1. Web dashboard for status, stream controls, config, music, logs.
2. Music (local files AND Spotify) addable/removable/changeable **live, without restarting the stream**.
3. 24/7 unattended operation: automatic detection and recovery from print end, print failure, stream/encode/audio death, disconnects.
4. Device-management feel (like Mainsail/Mainsail-like), incl. Mainsail integration.

## Non-Goals (v1)

- No authentication (dashboard binds to 127.0.0.1 local only; config key for future).
- No per-OS desktop/tray app (web dashboard covers it).
- No multi-printer management (out of scope; VMS already handles fleets).
- No Mainsail feature duplication — only link/embed.

## Architecture

```
python -m spoolup
   ├── Streaming runtime (main thread; unchanged behavior + watchdog)
   ├── Audio server      (spoolup/audio_server.py — daemon thread/editor:
   │                        stable PCM pipe → main ffmpeg's audio input)
   ├── Dashboard server  (spoolup/dashboard/ — FastAPI in daemon thread,
   │                      http://127.0.0.1:8007, no auth by design)
   └── Watchdog          (spoolup/watchdog.py — 30s health sweep + self-repair)
```

Isolation rule: dashboard/audio watchdog failures must never take streaming down; crash containment is per-thread with try/except wrappers, fallback to silence + banner on audio issues.

### Components

1. **`spoolup/dashboard/app.py`** — FastAPI app (Jinja2 templates + static; poll `/api/status` every 2 s; no websockets for v1).
2. **`spoolup/dashboard/state.py`** — bridge between UI and runtime:
   - snapshot unsafe-free read-only access to StreamManager, FramePump, MoonrakerClient, uploader
   - action endpoints post small commands into a queue consumed by runtime thread (start/stop/restart stream, activate music, save config)
3. **`spoolup/audio_server.py`** — owns ONE stable PCM audio pipe consumed by main ffmpeg (`-f s16le -ar 44100 -ac 2 -i pipe:3`):
   - Sources: silence (default), local files / playlists (sequential + loop), Spotify (librespot headless wrapper)
   - Hot-swap: swap source process underneath the pipe; main encode never stops; ≤0.5 s cross-fade handled by `afade`
   - Volume: applied in audio-server filter chain
   - Fallback: any source error → silence + dashboard warning banner
4. **`spoolup/watchdog.py`** — periodic checks, self-healing (see table below).
5. **Templates** — Dashboard / Settings (or wizard) / Music / Logs / Printer (Mainsail embed).

### Pages

| Page | Contents | Actions |
|---|---|---|
| Dashboard | Print card (state, progress, layers, temps — `MoonrakerClient.get_print_stats()`), Stream card (per-sink status: YT watch URL + health, Kick RTMP/SRT up/down, pump fps/dup/buffer), uploads summary, session history, uptime | **Start / Stop / Restart stream** |
| Settings | Friendly form for every `config.json` key with validation; test-buttons (test webcam / test Moonraker); secret fields masked with per-field show-toggle; `youtube_token.json` drag-drop upload | Save config (validated) |
| Music | Library (upload/preview/delete MP3s → `data/audio/`), playlist editor (ordered, live-modifiable), source selector (Silence / Local / Spotify), volume slider | All music changes live, no stream restart |
| Logs | Live tail of last ~200 lines (auto-scroll) | Filter by level |
| Printer | Embedded iframe of Mainsail (`http://<printer>:4409`) + quick links | none (already provided by Mainsail) |

**First-run wizard:** if `config.json` is missing, the dashboard boots into wizard page instead of dashboard: step-by-step form (printer IP, webcam URL, YouTube/Kick setup, token upload drop-zone). Produces a valid `config.json`; then redirects to Dashboard.

### In-app updates (new requirement, 2026-09-14)

The application self-updates from the dashboard — no CLI needed:

- **Check** (`POST /api/update/check`): `git fetch origin main`, compares `HEAD..origin/main`; returns the list of new commits (hash + `.subject` — effectively a changelog) or "already up to date". Never mutates the working tree.
- **Manual update** (`POST /api/update/apply`): worker thread runs `git pull` + `pip install -r requirements.txt` (output captured to log), then requests an application restart.
- **Auto-update** (`config.auto_update_enabled: true`, default): the dashboard checks every `2h` (`config.auto_update_interval_h`); if updates found → pull + requirements install happens immediately, then restart staging (below).
- **Live-stream protection (hard rule):** while `is_streaming == true`:
  - `update/apply` may pull files and refresh deps **but MUST NOT restart the runtime**, and must not touch `StreamManager`/ffmpeg in any way,
  - the restart is **deferred**: a `pending_restart` flag is set and visible as a banner; the restart executes automatically at the moment the stream ends (print complete/cancelled or manual stop via dashboard),
  - auto-update never enters the restart path while live — it only stages.
- **Restart executor:** after the stream ends (standby mode), if code changed on disk relative to the running process, the runtime stops the streaming threads cleanly and re-execs itself (same argv, same service wrapper) — on Windows via `subprocess.Popen([sys.executable, -m spoolup, -c config], CREATE_NEW_PROCESS...)` followed by prompt exit; on POSIX `os.execv` (same PID, service-safe).
- The dashboard shows: current commit version fingerprint, "X new commits available" badge, changelog list, update progress and the deferred-restart banner.
- Requirements pin change: if `requirements.txt` changed, `pip install` runs inside the current venv/system env; failures logged but never crash the app (config "Update failed, retry available" banner).

### API surface (v1) additions

- `POST /api/update/check` · `POST /api/update/apply` (returns "applied+restarting" or "staged — applies when stream ends")
- `GET  /api/update/status` (current/fetched commit, pending_restart flag, auto-update next-run time)

- `GET  /api/status` — snapshot {print, stream{sinks[], pump}, audio, health, uptime, banners}
- `POST /api/stream/start` · `POST /api/stream/stop` · `POST /api/stream/restart`
- `GET  /api/config` · `PUT  /api/config` (validated; secret keys masked on GET)
- `POST /api/config/test-webcam` · `POST /api/config/test-moonraker`
- `GET  /api/music` · `POST /api/music` (upload) · `DELETE /api/music/{id}`
- `POST /api/music/playlist` (update list, order, active source) · `POST /api/music/{id}/activate`
- `POST /api/audio/{action}` (set volume, mute, unmute)
- `GET  /api/logs?limit=200`
- `GET  /api/sessions` — recent print-session history
- `GET  /health-local` — tiny state endpoint (used by nothing external; service health)

### Config additions (all optional, backward compatible)

| Key | Default | Meaning |
|---|---|---|
| `dashboard_enabled` | `true` | Enables the dashboard thread |
| `dashboard_host` | `127.0.0.1` | Bind address — set `0.0.0.0` for LAN access from other devices (then no-password exposure is a documented user choice; recommended: firewall the port) |
| `dashboard_port` | `8007` | Port for the FastAPI dashboard |
| `auto_update_enabled` | `true` | Periodic check-and-stage updates |
| `auto_update_interval_h` | `2` | Hours between auto update checks |
| `audio_default_volume` | `0.8` | Initial audio-server volume |
| `keep_stream_on_error` | `true` | Matches current streaming behavior on Klipper errors |
| `watchdog_interval` | `30` | seconds between sweeps |
| `librespot_path` | `""` | empty = Spotify disabled, wizard hides the option |
| `data_dir` | `<repo>/data` | uploads/music, sessions, custom log dir |

### Print lifecycle / 24/7 idle behavior

- `printing` → stream starts (existing). `complete` → stop + upload + **standby mode** (all subsystems licensed for reuse, ready state)
- print `cancelled` or `error` → keep streaming until `complete`/`cancelled` (or immediate stop if `keep_stream_on_error: false`), then standby
- Each print owns a session record stored in `data/sessions.json` (last 50 sessions); displayed on dashboard for at-a-glance 7/24 health whenever the owner opens the UI.
- Upload pipeline unchanged (YouTubeUploader on completion)

## Watchdog decisions (self-heal table)

| Watched element | Reaction on failure | Dashboard banner |
|---|---|---|
| ffmpeg process dead / pump stats frozen → progress stalls | `_restart_ffmpeg_stream` | red: "restarted video encode" |
| FramePump disconnected > 60 s across retries | force reconnect cycle | yellow |
| Moonraker WS disconnected | existing reconnect loop continues; status stays visible | yellow (not red) |
| Audio server dead | restart in silence mode | yellow "audio restarted" |
| Klipper stream health bad | existing YouTube-health restart path | green note |
| Unexpected thread exception | log + isolate; streaming continues | red unless it affects the daemon |
| Process crash | external service restart (manage_service / spoolup.service) | dashboard shows uptime after recovery |

## Testing Strategy

- **Unit**: playlist sequencing + hot-swap transition logic (fake sources), config form validation, watchdog matrix (fake subsystems)
- **FastAPI TestClient** for all endpoints (no network)
- **Integration (dev machine)**: synthetic WAV → audio server → PCM pipe → local ffmpeg file capture; confirm hot-swap under 1 s and silence fallback
- **Manual on user machine**: Spotify account flow, 24/7 idle+print soak, Mainsail iframe embed (printer-specific)

## Security posture (v1)

- Default binding is localhost (`127.0.0.1`); `dashboard_host` is configurable for LAN/other-device access per user choice.
- No auth in v1: with `dashboard_host=0.0.0.0`, anyone on the LAN can control streams, edit config keys (masked display only), and see bind info — the spec treats that as acceptable only when the operator explicitly opts in (their network, their machine); recommend firewalling when exposing.
- Stream keys remain masked in all HTTP responses (form GET shows `***` with per-field show toggle)
- librespot credentials stored `0600`-equivalent in `data/spotify.json`; never logged
- No upstream HTTP calls added beyond what the runtime already does

## Out of scope (v1)

- Auth/login (documented future option)
- Multi-printer management
- Rebuilding Mainsail feature set
- Remote (non-localhost) exposure links (deployment user's responsibility if they want)

## Risks

- **librespot is unofficial Spotify**: requires Premium; account may theoretically be flagged; user accepted the trade-off
- **PCM pipe coupling**: audio-server bug could starve ffmpeg input; mitigated by silence-fill fallback and watchdog restart
- **Windows service + FastAPI thread**: uvicorn must not die with Ctrl+C handling; verified in implementation
- **Long-run stability**: memory growth from log tail / session JSON; mitigated with ring buffers and file rotation
