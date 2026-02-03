# Agent Guidelines for SpoolUp

## Project Overview
A Python application for Klipper-based 3D printers that streams live video to YouTube during prints and uploads timelapse videos when complete. Integrates with Moonraker API and uses FFmpeg for streaming.

## Build/Test Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run setup verification tests
python test_setup.py

# Run the main application
python spoolup.py

# Run with custom config
python spoolup.py -c /path/to/config.json

# Authenticate with YouTube only
python spoolup.py --auth-only

# Create sample config
python spoolup.py --create-config
```

**Note:** This project uses a custom `test_setup.py` script for verification. It does not use pytest or unittest.

## Code Style Guidelines

### Language & Types
- **Python 3.7+** minimum
- Use **type hints** for function parameters and return values: `def func(name: str) -> Optional[Dict[str, Any]]:`
- Use `typing` imports: `Optional`, `Dict`, `Any`, `Callable`

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `YouTubeStreamer`, `MoonrakerClient`)
- **Functions/Variables**: `snake_case` (e.g., `create_live_stream`, `stream_url`)
- **Constants**: `UPPER_CASE` (e.g., `SCOPES`, `DEFAULTS`)
- **Private methods**: `_leading_underscore` (e.g., `_on_message`, `_find_timelapse`)

### Imports Order
1. Standard library (os, sys, json, time, logging, subprocess, pathlib, datetime, typing)
2. Third-party packages (requests, websocket, google.*)

### Formatting
- **Indentation**: 4 spaces
- **Quotes**: Double quotes for strings
- **Line length**: ~100 characters (follow existing patterns)
- **Trailing commas**: Use in multi-line dicts/lists

### Error Handling
- Always use `try/except` with specific exception types
- Log errors with `logger.error()` or `logger.exception()`
- Return `None` or `False` on failure for functions that expect success
- Use `Optional[T]` return types for functions that may fail

### Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- Log levels: `INFO` for normal operations, `ERROR` for failures, `WARNING` for issues
- Include context in log messages

### Classes & Structure
- Use docstrings for classes and public methods
- Initialize instance variables in `__init__`
- Use type annotations for all instance variables
- Group related functionality into cohesive classes

### Configuration
- Use the `Config` class pattern for settings
- Provide sensible defaults in `DEFAULTS` dict
- Support JSON config file loading

### WebSocket & API Patterns
- Use `websocket.WebSocketApp` with callback methods (`_on_open`, `_on_message`, `_on_error`, `_on_close`)
- Use `requests` for REST API calls
- Handle reconnection logic gracefully

### Security
- Never commit `client_secrets.json` or `youtube_token.json`
- Store credentials outside the repository
- Use OAuth2 flow for YouTube authentication

## File Organization
```
spoolup/
├── spoolup.py  # Main application
├── test_setup.py                 # Verification script
├── requirements.txt              # Dependencies
├── install.sh                    # Installation script
├── spoolup.service  # Systemd service
└── config.json                   # User configuration (not in repo)
```

## Key Dependencies
- `google-api-python-client` - YouTube Data API
- `google-auth-oauthlib` - OAuth2 authentication
- `websocket-client` - Moonraker WebSocket
- `requests` - HTTP client
- `ffmpeg` - External streaming tool

## Important Notes
- Application runs as a long-lived service with WebSocket connection
- Must handle disconnections and reconnections gracefully
- Uses subprocess for FFmpeg streaming
- File paths and URLs are configurable
- Target platform: Creality K1 Max and other Klipper-based printers
