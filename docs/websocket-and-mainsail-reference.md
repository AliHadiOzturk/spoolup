# Moonraker WebSocket & Mainsail Documentation

## Server Information

- **IP Address**: 192.168.1.115:4409
- **Hostname**: K1Max-8899
- **Web Interface**: Mainsail (nginx/1.17.7)
- **Klipper Version**: 09faed31-dirty
- **CPU**: 2 cores
- **Status**: Ready / Printing

---

## WebSocket Connection

### Endpoint
```
ws://192.168.1.115:4409/websocket
```

### Protocol
- JSON-RPC 2.0 over WebSocket
- Subscribe to objects for real-time updates
- Server pushes notifications automatically after subscription

---

## Message Types

### 1. `notify_status_update` (Most Frequent)

**Frequency**: ~4 updates/second during printing
**Purpose**: Real-time printer status changes

#### Format
```json
{
  "jsonrpc": "2.0",
  "method": "notify_status_update",
  "params": [
    {
      // Changed objects only - not all objects every time
      "print_stats": {
        "total_duration": 4748.55,
        "print_duration": 4373.11,
        "filament_used": 8834.00
      },
      "toolhead": {
        "estimated_print_time": 1299331.11
      },
      "extruder": {
        "temperature": 225.19
      },
      "heater_bed": {
        "temperature": 60.0
      }
    },
    1299363.25  // Event timestamp
  ]
}
```

#### Available Objects in Status Updates

| Object | Fields | Description |
|--------|--------|-------------|
| `print_stats` | `filename`, `total_duration`, `print_duration`, `filament_used`, `state`, `message`, `info.total_layer`, `info.current_layer`, `power_loss`, `z_pos` | Current print job statistics |
| `toolhead` | `homed_axes`, `axis_minimum`, `axis_maximum`, `position`, `estimated_print_time` | Toolhead position and state |
| `extruder` | `temperature`, `target`, `power` | Hotend temperature |
| `heater_bed` | `temperature`, `target`, `power` | Bed temperature |
| `gcode_move` | `speed_factor`, `extrude_factor` | G-code movement modifiers |
| `display_status` | `progress`, `message` | Display status (0.0-1.0 progress) |
| `system_stats` | `sysload`, `cputime` | System load |

#### Print States
- `printing` - Actively printing
- `paused` - Print paused
- `complete` - Print finished successfully
- `cancelled` - Print cancelled
- `error` - Error state (treated as transient)

### 2. `notify_proc_stat_update`

**Frequency**: ~1 update/second
**Purpose**: System resource monitoring

#### Format
```json
{
  "jsonrpc": "2.0",
  "method": "notify_proc_stat_update",
  "params": [
    {
      "moonraker_stats": {
        "time": 1778254862.91,
        "cpu_usage": 16.87,
        "memory": null,
        "mem_units": null
      },
      "cpu_temp": null,
      "network": {
        "lo": {
          "rx_bytes": 123456,
          "tx_bytes": 789012
        }
      }
    }
  ]
}
```

### 3. `notify_timelapse_event`

**Frequency**: Sporadic (every ~10-15 seconds during timelapse capture)
**Purpose**: Timelapse frame capture notifications

#### Format
```json
{
  "jsonrpc": "2.0",
  "method": "notify_timelapse_event",
  "params": [
    {
      "action": "newframe",
      "frame": "249",
      "framefile": "frame000249.jpg",
      "status": "success"
    }
  ]
}
```

#### Actions
- `newframe` - New timelapse frame captured
- `render` - Timelapse rendering started/completed

### 4. `response`

**Frequency**: Once per request
**Purpose**: Response to explicit queries

#### Format
```json
{
  "jsonrpc": "2.0",
  "result": {
    "eventtime": 1299362.99,
    "status": {
      "print_stats": { ... },
      "toolhead": { ... }
    }
  },
  "id": 1
}
```

---

## Subscribing to Objects

### Request Format
```json
{
  "jsonrpc": "2.0",
  "method": "printer.objects.subscribe",
  "params": {
    "objects": {
      "print_stats": null,
      "toolhead": null,
      "extruder": null,
      "heater_bed": null,
      "display_status": null,
      "gcode_move": null,
      "system_stats": null
    }
  },
  "id": 1
}
```

### Query Format (One-time)
```json
{
  "jsonrpc": "2.0",
  "method": "printer.objects.query",
  "params": {
    "objects": {
      "print_stats": null,
      "toolhead": null
    }
  },
  "id": 2
}
```

---

## Available Printer Objects

Full list from `/printer/objects/list`:

### Hardware
- `webhooks` - Connection status
- `mcu` - Main MCU
- `mcu nozzle_mcu` - Nozzle MCU
- `mcu leveling_mcu` - Leveling MCU
- `mcu rpi` - Raspberry Pi MCU
- `virtual_pins` - Virtual pin states

### Temperature
- `extruder` - Hotend
- `heater_bed` - Heated bed
- `temperature_sensor_*` - Named sensors
- `temperature_fan_*` - Temperature-controlled fans

### Motion
- `toolhead` - Current position, homing status
- `gcode_move` - Move modifiers
- `stepper_*` - Individual steppers

### Print Job
- `print_stats` - Current print statistics
- `virtual_sdcard` - SD card emulation
- `pause_resume` - Pause state

### Macros
- `gcode_macro_*` - All configured macros (xyz_ready, _IF_HOME_Z, _HOME_X, etc.)

### Other
- `display_status` - LCD/display status
- `output_pin_*` - Controllable pins
- `fan` - Part cooling fan
- `probe` - Z-probe
- `bed_mesh` - Bed mesh data

---

## HTTP API Endpoints

### Printer Info
```
GET /printer/info
```
```json
{
  "result": {
    "state": "ready",
    "state_message": "Printer is ready",
    "hostname": "K1Max-8899",
    "klipper_path": "/usr/share/klipper",
    "python_path": "/usr/share/klippy-env/bin/python",
    "log_file": "/usr/data/printer_data/logs/klippy.log",
    "config_file": "/usr/data/printer_data/config/printer.cfg",
    "software_version": "09faed31-dirty",
    "cpu_info": "2 core"
  }
}
```

### Server Info
```
GET /server/info
```
```json
{
  "result": {
    "klippy_connected": true,
    "klippy_state": "ready",
    "components": [
      "secrets", "template", "klippy_connection", "jsonrpc",
      "file_manager", "authorization", "job_state", "webcam",
      "timelapse", "update_manager"
    ],
    "registered_directories": ["config", "logs", "gcodes"]
  }
}
```

### File List
```
GET /server/files/list
```
Returns list of G-code files with paths, sizes, and modification times.

---

## Mainsail Web Interface

### Features
- Real-time printer monitoring
- G-code file management
- Print job control (start, pause, cancel)
- Temperature graphs and controls
- Timelapse management
- Configuration editor
- System updates

### Components Enabled
- `timelapse` - Automatic timelapse recording
- `webcam` - Live camera feed
- `job_queue` - Print queue management
- `history` - Print history tracking
- `update_manager` - Software updates

### File Structure
- Config: `/usr/data/printer_data/config/`
- Logs: `/usr/data/printer_data/logs/`
- G-code: `/usr/data/printer_data/gcodes/`
- Klipper: `/usr/share/klipper`
- Virtual env: `/usr/share/klippy-env/`

---

## Usage Notes

### For SpoolUp Integration
1. Connect to WebSocket on port 4409
2. Subscribe to `print_stats` and `display_status`
3. Monitor `state` field for print completion
4. Check `display_status.progress` for percentage (0.0-1.0)
5. Listen for `notify_timelapse_event` for frame capture sync

### Message Frequency During Print
- Status updates: ~4/second
- Process stats: ~1/second
- Timelapse events: ~1/10-15 seconds

### Important Fields for Streaming
- `print_stats.state`: `printing` | `complete` | `cancelled`
- `display_status.progress`: 0.0 to 1.0
- `print_stats.filename`: Current G-code file
- `print_stats.total_duration`: Total time elapsed
- `print_stats.print_duration`: Active print time

### Error Handling
- Error state is treated as transient (like pause)
- Stream should continue during error state
- Only stop streaming on `complete` or `cancelled`
