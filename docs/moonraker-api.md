# Moonraker API Integration Guide

## Overview
This document details how the Video Management System communicates with 3D printers via the Moonraker API to discover and download timelapse videos.

## Architecture

### Network Setup
- **Server**: Runs Video Management System (this application)
- **Printer**: Klipper-based 3D printer with Moonraker
- **Connection**: Via Tailscale VPN (configured externally)
- **Protocol**: HTTP REST API + WebSocket
- **Base URL**: Configured per printer (e.g., `http://192.168.1.115:4409/`)

### No Local Filesystem Access
The application does NOT have direct filesystem access to the printer. All communication is via HTTP API calls over the network.

## Moonraker API Endpoints

### 1. Server Information
Check server status and capabilities.

**Endpoint:**
```
GET /server/info
```

**Example Response:**
```json
{
  "result": {
    "klippy_connected": true,
    "klippy_state": "ready",
    "components": ["timelapse", "update_manager"],
    "failed_components": [],
    "registered_directories": ["config", "logs", "timelapse"],
    "warnings": [],
    "websocket_count": 1,
    "moonraker_version": "v0.8.0"
  }
}
```

**Python Implementation:**
```python
import requests

def check_server_status(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/server/info", timeout=5)
        response.raise_for_status()
        data = response.json()
        return data["result"]["klippy_connected"]
    except Exception as e:
        logger.error(f"Failed to connect to Moonraker: {e}")
        return False
```

### 2. List Timelapse Files
Retrieve list of available timelapse videos.

**Endpoint:**
```
GET /server/files/list?root=timelapse
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| root | string | Yes | Must be "timelapse" |

**Example Response:**
```json
{
  "result": [
    {
      "path": "test_print_20240101_120000.mp4",
      "modified": 1704110400.0,
      "size": 15728640,
      "permissions": "rw"
    },
    {
      "path": "benchy_20240102_080000.mp4",
      "modified": 1704182400.0,
      "size": 23456789,
      "permissions": "rw"
    }
  ]
}
```

**Python Implementation:**
```python
def list_timelapse_files(base_url: str) -> List[Dict]:
    try:
        response = requests.get(
            f"{base_url}/server/files/list?root=timelapse",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return data.get("result", [])
    except Exception as e:
        logger.error(f"Failed to list timelapse files: {e}")
        return []
```

### 3. Download Timelapse File
Download a specific timelapse video file.

**Endpoint:**
```
GET /server/files/timelapse/{filename}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| filename | string | Yes | Name of the timelapse file |

**Example Request:**
```bash
curl -o video.mp4 "http://192.168.1.115:4409/server/files/timelapse/test_print_20240101_120000.mp4"
```

**Python Implementation:**
```python
def download_timelapse(base_url: str, filename: str, local_path: str) -> bool:
    try:
        url = f"{base_url}/server/files/timelapse/{filename}"
        
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    # Log progress every MB
                    if downloaded % (1024 * 1024) == 0:
                        progress = (downloaded / total_size * 100) if total_size else 0
                        logger.info(f"Download progress: {progress:.1f}%")
        
        logger.info(f"Downloaded {filename} to {local_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to download {filename}: {e}")
        return False
```

### 4. Get Timelapse Settings
Retrieve timelapse configuration from Moonraker.

**Endpoint:**
```
GET /server/timelapse/settings
```

**Example Response:**
```json
{
  "result": {
    "enabled": true,
    "mode": "layer",
    "camera": "",
    "snapshoturl": "http://localhost:8080/?action=snapshot",
    "stream_delay_compensation": 0.05,
    "gcode_verbose": false,
    "parkhead": false,
    "parkpos": "back_left",
    "park_custom_pos_x": 10.0,
    "park_custom_pos_y": 10.0,
    "park_custom_pos_dz": 2.0,
    "park_travel_speed": 100,
    "park_retract_speed": 15,
    "park_extrude_speed": 15,
    "park_retract_distance": 1.0,
    "park_extrude_distance": 1.0,
    "hyperlapse_cycle": 30,
    "autorender": true,
    "constant_rate_factor": 23,
    "output_framerate": 30,
    "pixelformat": "yuv420p",
    "time_format_code": "%Y%m%d_%H%M%S",
    "variable_fps": false,
    "targetlength": 10,
    "min_framerate": 5,
    "max_framerate": 60,
    "rotation": 0,
    "dublicatelastframe": 5,
    "previewimage": true,
    "saveframes": false
  }
}
```

### 5. WebSocket API (Optional)
Real-time notifications from Moonraker.

**Connection URL:**
```
ws://{printer_ip}:{port}/websocket
```

**Example:**
```
ws://192.168.1.115:4409/websocket
```

**Key Notifications:**
- `notify_gcode_response` - G-code execution status
- `notify_status_update` - Printer status changes
- `notify_timelapse_event` - Timelapse capture events

**Python Implementation:**
```python
import websocket
import json

def on_message(ws, message):
    data = json.loads(message)
    if data.get("method") == "notify_timelapse_event":
        params = data.get("params", {})
        event = params.get("event")
        if event == "complete":
            logger.info("Timelapse recording completed")
            # Trigger video sync

ws = websocket.WebSocketApp(
    "ws://192.168.1.115:4409/websocket",
    on_message=on_message,
    on_error=lambda ws, e: logger.error(f"WebSocket error: {e}"),
    on_close=lambda ws: logger.info("WebSocket closed")
)
ws.run_forever()
```

## Video Discovery Workflow

### Step-by-Step Process

1. **Check Printer Connection**
   ```python
   if not check_server_status(printer_url):
       logger.error("Printer is offline")
       return
   ```

2. **List Available Timelapses**
   ```python
   files = list_timelapse_files(printer_url)
   ```

3. **Compare with Database**
   ```python
   known_files = get_known_videos_from_db()
   new_files = [f for f in files if f["path"] not in known_files]
   ```

4. **Download New Videos**
   ```python
   for file_info in new_files:
       local_path = f"/tmp/timelapse/{file_info['path']}"
       if download_timelapse(printer_url, file_info["path"], local_path):
           # Extract metadata
           metadata = extract_video_metadata(local_path)
           # Save to database
           save_video_to_db(file_info, metadata)
   ```

5. **Detect Deleted Videos**
   ```python
   current_files = {f["path"] for f in files}
   for known in known_files:
       if known["filename"] not in current_files:
           mark_video_deleted(known["id"])
   ```

### Full Implementation Example
```python
class MoonrakerClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"X-API-Key": api_key})
    
    def is_connected(self) -> bool:
        try:
            response = self.session.get(
                f"{self.base_url}/server/info",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def get_timelapse_list(self) -> List[Dict]:
        response = self.session.get(
            f"{self.base_url}/server/files/list?root=timelapse",
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("result", [])
    
    def download_file(self, filename: str, local_path: str) -> bool:
        url = f"{self.base_url}/server/files/timelapse/{filename}"
        
        try:
            with self.session.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
```

## Printer Configuration

### Multiple Printer Support
The system supports multiple printers:

```python
printers = [
    {
        "name": "K1 Max Office",
        "moonraker_url": "http://192.168.1.115:4409",
        "moonraker_port": "4409",
        "api_key": None
    },
    {
        "name": "K2 Plus Garage",
        "moonraker_url": "http://192.168.1.120:4409",
        "moonraker_port": "4409",
        "api_key": "optional_key"
    }
]
```

### Database Schema
```sql
CREATE TABLE printers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    moonraker_url TEXT NOT NULL,
    moonraker_port TEXT DEFAULT '4409',
    api_key TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Sync Scheduler

### Automatic Sync
Run periodic sync to discover new videos:

```python
from apscheduler.schedulers.background import BackgroundScheduler

def sync_all_printers():
    printers = get_all_printers()
    for printer in printers:
        if not printer.is_active:
            continue
        
        client = MoonrakerClient(
            printer.moonraker_url,
            printer.api_key
        )
        
        if not client.is_connected():
            logger.warning(f"Printer {printer.name} is offline")
            continue
        
        files = client.get_timelapse_list()
        process_new_files(printer.id, files)
        detect_deleted_files(printer.id, files)
        update_last_sync(printer.id)

# Schedule every 15 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(sync_all_printers, 'interval', minutes=15)
scheduler.start()
```

### Manual Sync
```bash
# Trigger sync via API
POST /api/printers/{id}/sync
```

## Error Handling

### Common Errors
| Error | Cause | Solution |
|-------|-------|----------|
| Connection timeout | Printer offline or network issue | Check Tailscale connection |
| 404 Not Found | File deleted or path changed | Update file list |
| 403 Forbidden | Missing API key | Configure API key in printer settings |
| Incomplete download | Network interruption | Resume or retry download |
| Disk full | Server storage full | Clean up old files or expand storage |

### Retry Strategy
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def download_with_retry(client, filename, local_path):
    return client.download_file(filename, local_path)
```

## Security Considerations

### API Keys
- Moonraker may be configured with API key authentication
- Store API keys encrypted in database
- Use HTTPS when available (not standard on Moonraker)

### Network Security
- Tailscale provides encrypted tunnel
- No direct port exposure to internet
- Application server is the only entry point

### File Validation
- Validate downloaded files are valid video files
- Check file integrity (size matches expected)
- Scan for malicious content (if possible)

## Performance Optimization

### Download Optimization
- Use streaming downloads (no memory buffering)
- Parallel downloads for multiple files
- Resume interrupted downloads (if supported)

### Storage Management
- Delete local copies after upload to platforms
- Keep only metadata in database
- Archive old videos to cold storage (optional)

### Caching
- Cache printer connection status
- Cache file lists (refresh every sync)
- Don't re-download known files

## Monitoring

### Metrics to Track
- Printer connection status
- Files discovered per sync
- Download success/failure rate
- Time to download files
- Disk usage on server

### Logging
```python
logger.info(f"Discovered {len(new_files)} new videos on {printer.name}")
logger.info(f"Downloaded {filename} ({size_mb:.1f} MB) in {duration:.1f}s")
logger.warning(f"Printer {printer.name} is offline")
logger.error(f"Failed to download {filename}: {error}")
```

## Testing

### Test Environment
- Use test printer or mock server
- Verify network connectivity first
- Test with small files initially

### Mock Server
```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/server/info')
def server_info():
    return jsonify({
        "result": {
            "klippy_connected": True,
            "klippy_state": "ready"
        }
    })

@app.route('/server/files/list')
def list_files():
    return jsonify({
        "result": [
            {"path": "test.mp4", "size": 1024}
        ]
    })
```

## References
- [Moonraker Documentation](https://moonraker.readthedocs.io/)
- [Klipper Documentation](https://www.klipper3d.org/)
- [Moonraker GitHub](https://github.com/Arksine/moonraker)
- [Timelapse Plugin](https://github.com/mainsail-crew/moonraker-timelapse)
