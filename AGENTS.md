# PROJECT KNOWLEDGE BASE

**Generated:** 2026-09-12
**Commit:** 44f837f
**Branch:** main

## OVERVIEW
A multi-component project for Klipper-based 3D printers:

- **`spoolup/`** — Streaming machine runtime (PC/Mac/server — NOT on the printer): monitors Moonraker over the network, streams live video to YouTube + Kick (single ffmpeg encode, tee muxer, buffered MJPEG ingest via `frame_pump.py`), uploads timelapses on completion. Split architecture: authentication on PC/Mac (`spoolup_auth/`).
- **`video_management/`** — Self-contained FastAPI web app (VMS): discovers timelapses from Moonraker printers, processes them to 9:16 vertical, uploads to YouTube Shorts and TikTok, with analytics dashboard and midnight sync. See `video_management/README.md`.
- **`landing/`** — Static marketing site (plain HTML/CSS/JS), deployed to Cloudflare Workers via root `wrangler.jsonc`. See `landing/README.md`.

Reference docs for external APIs live in `docs/` (index: `docs/api-integration-index.md`).

## Build/Test/Lint Commands

```bash
# Install runtime dependencies (on printer)
pip install -r requirements.txt

# Install auth dependencies (on PC/Mac)
pip install -r requirements-auth.txt

# Run setup verification
python test_setup.py

# Run the main application (from virtualenv)
python -m spoolup -c /path/to/config.json

# Authenticate with YouTube (on PC/Mac)
python -m spoolup_auth --client-secrets /path/to/client_secrets.json

# Run syntax check on Python files
python -m py_compile spoolup/main.py spoolup_auth/main.py

# Lint with ruff (if available)
ruff check spoolup/ spoolup_auth/
ruff check --fix spoolup/ spoolup_auth/

# Type check with mypy (optional)
mypy spoolup/ spoolup_auth/

# Video Management System (from video_management/, needs its own venv)
cd video_management && ./setup.sh        # create venv, install deps, init DB
source venv/bin/activate && python main.py
find . -name "*.py" -not -path "./venv/*" | xargs python -m py_compile  # syntax check

# Landing site (static, no build)
python -m http.server 8080 -d landing    # local preview
npx wrangler deploy                      # deploy to Cloudflare
```

**Note:** This project uses a custom `test_setup.py` script for verification. It does not use pytest or unittest. Individual test functions cannot be run separately - run the entire script.

## Code Style Guidelines

### Language & Types
- **Python 3.7+** minimum
- Use **type hints** for function parameters and return values: `def func(name: str) -> Optional[Dict[str, Any]]:`
- Use `typing` imports: `Optional`, `Dict`, `Any`, `Callable`, `List`, `Union`
- Always import from `typing` module, not built-in generics (for 3.7 compatibility)

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `YouTubeStreamer`, `MoonrakerClient`)
- **Functions/Variables**: `snake_case` (e.g., `create_live_stream`, `stream_url`)
- **Constants**: `UPPER_CASE` (e.g., `SCOPES`, `DEFAULTS`)
- **Private methods/variables**: `_leading_underscore` (e.g., `_on_message`, `_find_timelapse`)
- **Module-level logger**: `logger = logging.getLogger(__name__)`

### Imports Order
1. Standard library (os, sys, json, time, logging, subprocess, pathlib, datetime, typing)
2. Third-party packages (requests, websocket, google.*)
3. Local modules (spoolup.*)

### Formatting
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings
- **Line length**: ~100 characters
- **Trailing commas**: Use in multi-line dicts/lists
- **Blank lines**: 2 lines between top-level definitions, 1 line between methods

### Error Handling
- Always use `try/except` with specific exception types
- Log errors with `logger.error()` or `logger.exception()` for stack traces
- Return `None` or `False` on failure for functions that expect success
- Use `Optional[T]` return types for functions that may fail
- Never catch bare `Exception` unless re-raising

### Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- Log levels: `INFO` for normal operations, `ERROR` for failures, `WARNING` for issues
- Include context in log messages: `logger.info(f"Stream started: {stream_id}")`
- Never use `print()` in production code

### Classes & Structure
- Use docstrings for classes and public methods
- Initialize instance variables in `__init__`
- Use type annotations for all instance variables
- Group related functionality into cohesive classes
- Use `@property` for computed attributes

### Configuration
- Use the `Config` class pattern for settings
- Provide sensible defaults in `DEFAULTS` dict
- Support JSON config file loading
- Validate config values on load

### WebSocket & API Patterns
- Use `websocket.WebSocketApp` with callbacks (`_on_open`, `_on_message`, `_on_error`, `_on_close`)
- Use `requests` for REST API calls
- Handle reconnection logic gracefully with exponential backoff
- Set appropriate timeouts on all network calls

### Security
- Never commit `client_secrets.json` or `youtube_token.json`
- Store credentials outside the repository
- Use OAuth2 flow for YouTube authentication
- Never log sensitive tokens or credentials

## ANTI-PATTERNS (THIS PROJECT)

- **Never catch bare `Exception`** unless re-raising
- **Never use `print()`** in production code — use `logger` exclusively
- **Never commit credential files** (`client_secrets.json`, `youtube_token.json`)
- **Never log sensitive tokens** or credentials
- **Never modify `spoolup.py`** — it is deprecated
- **Never install OAuth libraries** into the runtime (use split requirements)
- Do NOT switch away from hardware encoding (`h264_qsv`) unless fallback needed
- Do NOT change fundamental architecture (keep MJPEG input, RTMP output)
- Do NOT break existing configs — maintain backward compatibility

## NOTES

### Architecture
- **Split design**: Auth separate from runtime; runtime runs on a PC/streaming machine, connecting to the printer over the network (printer CPUs can't sustain live encoding)
- Runtime loads token from `youtube_token.json` (no OAuth flow in the runtime)
- Runtime package intentionally excludes OAuth libraries

### Repository Layout
- `spoolup/`, `spoolup_auth/` — streaming-machine runtime + PC/Mac auth tool (see `spoolup/AGENTS.md`)
- `video_management/` — self-contained FastAPI VMS with its own venv, SQLite DB, and Alembic migrations (see `video_management/README.md`)
- `landing/` — static marketing site served as Cloudflare Workers assets (see `landing/README.md`)
- `docs/` — external API references (YouTube, TikTok, Moonraker), Docker guides, short-form video standards
- `install.sh` — interactive installer for embedded/generic Linux (printer-class hardware typically cannot sustain live encoding — legacy path)
- `install_k1.sh`, `install_generic.sh`, `install_universal.py`/`install_universal.sh` — platform-specific/universal installer variants
- `manage_service.py`/`manage_service.sh` — universal service manager (systemd/init.d on Linux, launchd on macOS, schtasks on Windows)
- `spoolup.service`, `docker-compose.yml`, `DOCKER_IMPLEMENTATION.md` — systemd unit and Docker deployment for the VMS

### Video Management System (VMS)
- Self-contained: everything runs inside `video_management/` with its own `venv/`
- FastAPI + Jinja2 UI, SQLite via SQLAlchemy, JWT auth, Alembic migrations
- Upload pipeline: `upload_queue/` (manager, worker, scheduler) with retry/cancel
- Post-processing: `post_processing/` (audio mixer, editor, filters, text overlays)
- Security: login rate limiting, security headers middleware, `ALLOW_REGISTRATION=false` default, audit log — see `SECURITY.md`
- Video streaming proxy (`/api/videos/{id}/stream`, `/api/videos/{id}/thumbnail`) supports token in query params for `<video>`/`<img>` tags

### Installation
- Standard path: pip install requirements and `python -m spoolup -c config.json` on the streaming machine
- Embedded-Linux installer exists (`install.sh`, `/usr/data/spoolup-env` K1 / `/opt/spoolup-env` generic) but printer-class hardware cannot sustain live encoding — legacy

### Running
- Runtime: `python -m spoolup -c config.json`
- Auth: `python -m spoolup_auth --client-secrets client_secrets.json`
- Service: `manage_service.py` (systemd/init.d/launchd/schtasks) or manual `python -m spoolup -c config.json`

### Target Environments
- Any PC/Mac/Linux machine with network access to the printer (Windows supported: QSV/NVENC detection included)
- Printers are accessed over the network only (Moonraker + MJPEG webcam)

### Development Tips
- Always run `python -m py_compile` to check syntax before committing
- Test auth on PC/Mac and the runtime on the streaming machine (config points at printer over LAN)
- Use `logger` for all output, avoid `print()` in production code
- Handle WebSocket disconnections gracefully with reconnection logic
- Use `--auth-only` flag to test authentication without streaming
- Use `--create-config` flag to generate a default config file

### Threading & Concurrency
- Use `threading.Thread` for background tasks
- Use `threading.Event` for graceful shutdown signals
- Always set `daemon=True` for background threads
- Clean up resources in `finally` blocks or context managers

### Dependencies Note
- **cryptography package is NOT included** - OAuth2 user token flow does not require it
- Service account authentication would need cryptography (RSA signing), but SpoolUp uses user OAuth
- HTTPS/TLS is handled by Python's `ssl` module and system OpenSSL
- This avoids compilation issues on embedded systems (MIPS) without a C compiler

### Error State Handling
- SpoolUp treats Klipper "error" state as transient (similar to a pause)
- Live stream continues during error state - no interruption
- If print recovers and resumes, stream continues automatically
- Stream only stops on "complete" or "cancelled" states
- This prevents transient errors from interrupting live streams
