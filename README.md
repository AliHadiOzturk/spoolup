# SpoolUp 🎬🖨️

> **SpoolUp and go live!** Automatically stream your 3D prints to YouTube Live and Kick, and upload timelapses when done.

SpoolUp is a Python application that connects your Klipper-based 3D printer (like the Creality K1 Max) to YouTube and Kick. It runs **on your PC / streaming machine** — not on the printer — and monitors the printer over the network via Moonraker. When you start a print, it automatically begins a live stream with a single shared encode to both platforms. When your print finishes, it uploads the timelapse video as a draft to your YouTube channel.

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-orange)

## ✨ Features

- 🎥 **Automatic Live Streaming** - Starts a YouTube Live stream when your print begins
- 🎯 **Dual destination** - Single ffmpeg encode fans out to YouTube AND Kick simultaneously
- 🛡️ **Buffered ingest** - Frame pump absorbs webcam stalls (no more `videoIngestionStarved` / progressive lag)
- 📹 **Timelapse Upload** - Automatically uploads timelapse videos as private drafts when prints complete
- 🔗 **Native Klipper Integration** - Works seamlessly with Moonraker API
- ⚙️ **Easy Configuration** - Simple JSON configuration file
- 🚀 **Real-time Detection** - Monitors print status via WebSocket for instant response
- 📱 **Notifications** - Sends print status updates with stream URLs
- 🐳 **Service Mode** - Can run as a systemd/launchd/schtasks service for always-on operation
- 🔒 **Separate Authentication** - Authenticate on your PC/Mac, run the runtime anywhere

## 📋 Requirements

### Streaming Machine (PC, Mac, home server, NAS — anything but the printer)
- Python 3.7 or higher
- Git (for cloning the repository)
- FFmpeg installed on your system (with `h264` encoder; CPU or hardware)
- Network access to the printer's Moonraker API and webcam stream

### On Your PC/Mac
- YouTube Data API v3 credentials
- Python 3.7+ (for authentication tool)

## 🏗️ Architecture

SpoolUp uses a **split architecture**: authentication tooling stays out of the runtime, and the runtime never runs on the printer (printer CPUs/GPUs are too weak for live encoding):

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR PC / MAC                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  spoolup-auth                                       │   │
│  │  • Runs OAuth flow with browser                     │   │
│  │  • Generates youtube_token.json                     │   │
│  │  • Needs: google-auth-oauthlib                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                               │                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SpoolUp Runtime                                    │   │
│  │  • Monitors Moonraker WebSocket (printer on LAN)    │   │
│  │  • FramePump: buffered ingest of MJPEG webcam       │   │
│  │  • Single ffmpeg encode → tee →                     │   │
│  │      rtmp/FLV → YouTube                             │   │
│  │      (rtmp|srt)  → Kick                             │   │
│  │  • Uploads timelapses                               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Why this approach?**
- **Hardware headroom** - Live encoding is real work; printer SoCs can't sustain it
- **Network-only printer access** - The runtime just talks Moonraker + webcam HTTP
- **Separate auth** - OAuth flow happens once on PC; runtime just loads the token

## 🚀 Quick Start

### Step 1: Install SpoolUp on Your Streaming Machine

Clone the repo anywhere you like (PC, home server, NAS):

```bash
git clone https://github.com/AliHadiOzturk/spoolup.git
cd spoolup
pip install -r requirements.txt
```

On embedded Linux there is also `install.sh` (auto-detects K1/K2/Sonic Pad/generic Linux, creates a venv and a service) — but note that printer-class hardware usually cannot sustain live encoding; prefer a normal PC/system/NAS.

### Step 2: Get YouTube API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable **YouTube Data API v3**:
   - Go to "Library" in the left menu
   - Search for "YouTube Data API v3"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "Credentials" in the left menu
   - Click "Create Credentials" → "OAuth client ID"
   - Choose **"Desktop app"** as the application type
   - Give it a name (e.g., "SpoolUp")
   - Click "Create"
5. Download the client secrets:
   - Click the download icon next to your credentials
   - Save as `client_secrets.json` on your PC/Mac

### Step 3: Authenticate on Your PC/Mac

**Option A: Using pip (Recommended)**

```bash
# On your PC/Mac
pip install -r https://raw.githubusercontent.com/AliHadiOzturk/spoolup/main/requirements-auth.txt

# Run authentication
python -m spoolup_auth --client-secrets /path/to/client_secrets.json

# This creates youtube_token.json in your current directory
```

**Option B: Clone the repo**

```bash
# On your PC/Mac
git clone https://github.com/AliHadiOzturk/spoolup.git
cd spoolup
pip install -r requirements-auth.txt
python -m spoolup_auth --client-secrets /path/to/client_secrets.json
```

A browser window will open automatically. Sign in with your Google account and authorize SpoolUp.

### Step 4: Point the Token at Your Runtime

Keep `youtube_token.json` next to your `config.json` on the streaming machine (or set `token_file` in the config). Nothing is copied to the printer — the printer only serves Moonraker and the webcam stream over HTTP.

### Step 5: Start SpoolUp

```bash
# On the streaming machine
python -m spoolup -c config.json
```

**Run it as a service** for always-on operation: `manage_service.py` / `manage_service.sh` set this up on systemd/init.d (Linux), launchd (macOS), or schtasks (Windows).

### Step 6: Verify It's Working

Follow the console/log output — you'll see YouTube stream creation, health checks, and Kick connection status. Logs to `/var/log/spoolup.log` when service-managed (Linux).

## 🖥️ Running from Source (this is the standard way)

If you'd rather run SpoolUp with the repo venv / one-liner:

```bash
# Clone the repository
git clone https://github.com/AliHadiOzturk/spoolup.git
cd spoolup

# Install runtime dependencies
pip install -r requirements.txt

# Authenticate
pip install -r requirements-auth.txt
python -m spoolup_auth --client-secrets /path/to/client_secrets.json

# Run SpoolUp
python -m spoolup -c config.json
```

**Note:** Update `config.json` to point to your printer's IP:
```json
{
  "moonraker_url": "http://192.168.1.100:7125",
  "webcam_url": "http://192.168.1.100:8080/?action=stream",
  "timelapse_dir": "/path/to/timelapse"
}
```

## 📁 Project Structure

```
spoolup/
├── install.sh                 # Main installer (interactive shell script)
├── requirements.txt           # Core runtime dependencies (streaming machine)
├── requirements-auth.txt      # Auth dependencies (PC/Mac only)
├── README.md                  # This file
│
├── spoolup/                   # Runtime package (runs on the streaming machine)
│   ├── frame_pump.py          # Buffered MJPEG ingest (webcam → ffmpeg)
│   ├── main.py                # Core application (stream manager, NO auth flow)
│
└── spoolup_auth/              # Authentication tool (PC/Mac only)
    ├── __init__.py
    ├── __main__.py
    └── main.py               # OAuth flow with browser
```

## 🔧 Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `moonraker_url` | URL of your Moonraker instance | `http://localhost:7125` |
| `webcam_url` | URL of your MJPEG webcam stream | `http://localhost:8080/?action=stream` |
| `timelapse_dir` | Directory where timelapse videos are saved | `/home/user/printer_data/timelapse` |
| `client_secrets_file` | Path to Google OAuth client secrets | `client_secrets.json` |
| `token_file` | Path to save YouTube authentication token | `youtube_token.json` |
| `stream_resolution` | Live stream resolution | `1280x720` |
| `stream_fps` | Live stream frame rate | `30` |
| `stream_bitrate` | Live stream video bitrate | `4000k` |
| `stream_privacy` | Live stream privacy | `unlisted` |
| `video_privacy` | Uploaded timelapse privacy | `private` |
| `enable_live_stream` | Enable live streaming | `true` |
| `enable_timelapse_upload` | Enable timelapse upload | `true` |
| `kick_enabled` | Also push the live stream to Kick simultaneously | `false` |
| `kick_rtmp_url` | Kick RTMP ingest URL (Kick Creator dashboard) | `rtmp://fa723fc1b91d4.global-media-services.com:1935/live` |
| `kick_stream_key` | Kick stream key (keep secret; never commit) | `` |
| `ingest_buffer_seconds` | Webcam-side frame buffer absorbing camera stalls | `10` |

## 🐛 Troubleshooting

### "Token file not found"

Authenticate on your PC/Mac first, then place the token where `config.json`'s `token_file` points:
```bash
python -m spoolup_auth --client-secrets client_secrets.json
cp youtube_token.json /path/to/your/runtime/directory/
```

### "Credentials are invalid or expired"

Re-authenticate on your PC/Mac:
```bash
python -m spoolup_auth --client-secrets client_secrets.json
```
Then restart the runtime.

### FFmpeg not found

Install FFmpeg on the streaming machine:
```bash
# Windows
winget install Gyan.FFmpeg

# Linux
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

### Service won't start

Check the logs:
```bash
tail -n 50 /var/log/spoolup.log   # systemd/init.d installs
```

Verify the token file exists where `token_file` points from your `config.json`.

## 🔄 Updating SpoolUp

```bash
cd /path/to/spoolup
git pull
pip install -r requirements.txt
# restart your service / rerun python -m spoolup -c config.json
```

## 🗑️ Uninstalling

```bash
# If service-managed (Linux)
/etc/init.d/S99spoolup stop 2>/dev/null || sudo systemctl stop spoolup
rm -f /etc/init.d/S99spoolup /etc/systemd/system/spoolup.service

# Remove the repository / venv
rm -rf ~/spoolup ~/spoolup-env
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License - Feel free to modify and distribute.

## 🙏 Credits

- Uses [Klipper](https://www.klipper3d.org/) and [Moonraker](https://moonraker.readthedocs.io/)
- YouTube integration via [Google API Client](https://github.com/googleapis/google-api-python-client)

---

## 🎬 Video Management System (New!)

A new web-based video management system is now included for uploading timelapse videos to YouTube Shorts and TikTok.

### Features

- **Video Discovery**: Automatically discovers timelapse videos from Moonraker-based 3D printers
- **Video Processing**: Converts 16:9 raw footage to 9:16 vertical format using FFmpeg
- **Multi-Platform Upload**: Uploads to YouTube Shorts and TikTok using official APIs
- **Analytics Dashboard**: Tracks views, likes, comments, and shares with midnight sync
- **Web Interface**: Modern dashboard for managing videos, uploads, and analytics
- **Docker Support**: Easy deployment with Docker Compose

### Quick Start with Docker

```bash
# Clone and configure
git clone https://github.com/AliHadiOzturk/spoolup.git
cd spoolup
cp video_management/.env.example .env
# Edit .env with your settings

# Start with Docker Compose
docker-compose up -d

# Access the web interface at http://localhost:8000
```

For detailed setup, see:
- [Video Management System README](video_management/README.md)
- [Docker Setup Guide](docs/docker-setup.md)
- [Security Policy](SECURITY.md)

---

**Happy Printing! 🎉**

*SpoolUp - Because your prints deserve an audience.*
