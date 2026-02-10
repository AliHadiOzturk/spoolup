# Agent Guidelines for SpoolUp

## Project Overview
A Python application for Klipper-based 3D printers that streams live video to YouTube during prints and uploads timelapse videos when complete. Uses a split architecture: authentication on PC/Mac, runtime on printer.

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

## File Organization

```
spoolup/
├── spoolup/                      # Runtime package (runs on printer)
│   ├── __init__.py               # Exports main function
│   ├── __main__.py               # Entry point: python -m spoolup
│   └── main.py                   # Core streaming functionality
├── spoolup_auth/                 # Auth tool (runs on PC/Mac)
│   ├── __init__.py               # Exports main function
│   ├── __main__.py               # Entry point: python -m spoolup_auth
│   └── main.py                   # OAuth flow with browser
├── test_setup.py                 # Verification script
├── requirements.txt              # Runtime dependencies (NO OAuth libs)
├── requirements-auth.txt         # Auth dependencies (PC/Mac only)
├── install.sh                    # Main installer script (interactive)
├── install_k1.sh                 # K1-specific installer (legacy)
├── install_generic.sh            # Generic Linux installer (legacy)
├── spoolup.py                    # Legacy main file (deprecated)
├── spoolup.service               # Systemd service file
└── config.json                   # User configuration (not in repo)
```

## Key Dependencies

**Runtime (printer):**
- `google-api-python-client` - YouTube Data API
- `google-auth` - Core authentication (NO OAuth libs!)
- `websocket-client` - Moonraker WebSocket
- `requests` - HTTP client
- `ffmpeg` - External streaming tool

**Auth (PC/Mac):**
- `google-auth-oauthlib` - OAuth2 browser flow
- `google-auth-httplib2` - HTTP transport
- `google-api-python-client` - YouTube Data API

## Important Notes

### Architecture
- **Split design**: Auth on PC/Mac, runtime on printer
- Runtime loads token from `youtube_token.json` (no OAuth flow on printer)
- Saves ~50MB by not installing OAuth libraries on embedded systems

### Installation
- New installer: `git clone` then `sh install.sh` (interactive, box-drawn UI)
- Creates Python virtual environment at `/usr/data/spoolup-env` (K1) or `/opt/spoolup-env` (generic)
- Auto-detects OS: K1, K2, Sonic Pad, or generic Linux

### Running
- Runtime: `python -m spoolup -c config.json`
- Auth: `python -m spoolup_auth --client-secrets client_secrets.json`
- Service: `/etc/init.d/S99spoolup start` (K1) or `systemctl start spoolup` (systemd)

### Target Platforms
- Creality K1 / K1 Max / K1C / K2 Plus
- Creality Sonic Pad
- Generic Linux with systemd or init.d

### Development Tips
- Always run `python -m py_compile` to check syntax before committing
- Test on both PC/Mac (auth) and printer (runtime) environments
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
