# SpoolUp 🎬🖨️

> **SpoolUp and go live!** Automatically stream your 3D prints to YouTube Live and upload timelapses when done.

SpoolUp is a Python application that connects your Klipper-based 3D printer (like the Creality K1 Max) directly to YouTube. When you start a print, it automatically begins a live stream. When your print finishes, it uploads the timelapse video as a draft to your YouTube channel.

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Klipper-orange)

## ✨ Features

- 🎥 **Automatic Live Streaming** - Starts a YouTube Live stream when your print begins
- 📹 **Timelapse Upload** - Automatically uploads timelapse videos as private drafts when prints complete
- 🔗 **Native Klipper Integration** - Works seamlessly with Moonraker API
- ⚙️ **Easy Configuration** - Simple JSON configuration file
- 🚀 **Real-time Detection** - Monitors print status via WebSocket for instant response
- 📱 **Notifications** - Sends print status updates with stream URLs
- 🐳 **Service Mode** - Can run as a systemd service for always-on operation
- 🔒 **Separate Authentication** - Authenticate on your PC/Mac, run on your printer

## 📋 Requirements

### On Your Printer
- Python 3.7 or higher
- Git (for cloning the repository)
- FFmpeg installed on your system
- Klipper firmware with Moonraker API enabled
- A webcam configured with your Klipper setup

### On Your PC/Mac
- YouTube Data API v3 credentials
- Python 3.7+ (for authentication tool)

## 🏗️ Architecture

SpoolUp uses a **split architecture** to avoid installing unnecessary packages on your printer:

```
┌─────────────────────────────────────────────────────────────┐
│                    YOUR PC / MAC                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  spoolup-auth                                       │   │
│  │  • Runs OAuth flow with browser                     │   │
│  │  • Generates youtube_token.json                     │   │
│  │  • Needs: google-auth-oauthlib (NOT on printer!)    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ scp youtube_token.json
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    YOUR PRINTER (K1/etc)                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  SpoolUp Runtime                                    │   │
│  │  • Monitors Moonraker WebSocket                     │   │
│  │  • Streams to YouTube via FFmpeg                    │   │
│  │  • Uploads timelapses                               │   │
│  │  • Needs: google-api-python-client (NO OAuth libs)  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Why this approach?**
- **Smaller footprint** - No OAuth libraries on printer (saves ~50MB)
- **No browser needed** - Authentication happens on PC with browser
- **Easier setup** - Just copy a token file, no headless auth hassle
- **Proven on K1/K2** - Works reliably on Creality embedded Linux systems

## 🚀 Quick Start

### Step 1: Install SpoolUp on Your Printer

**For Creality K1 / K1 Max / K1C / K2:**

```bash
# SSH into your printer
ssh root@<your_printer_ip>

# Clone the repository and run the installer
git clone https://github.com/AliHadiOzturk/spoolup.git /tmp/spoolup
cd /tmp/spoolup
sh install.sh
```

The installer features:
- **Interactive confirmation** - You'll be asked to confirm before installation
- **Nice UI** - Box-drawn interface with clear status messages
- **OS auto-detection** - Automatically detects K1, K2, Sonic Pad, or generic Linux
- **Virtual environment** - Creates isolated Python environment
- **Service creation** - Sets up auto-start service for your init system

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

### Step 4: Copy Token to Your Printer

```bash
# On your PC/Mac, copy the token to your printer
scp youtube_token.json root@<printer_ip>:/usr/data/spoolup/
```

For Sonic Pad:
```bash
scp youtube_token.json root@<printer_ip>:/usr/share/spoolup/
```

### Step 5: Start SpoolUp

**For K1 / K2 / Sonic Pad:**
```bash
# SSH into printer and start the service
ssh root@<printer_ip>
/etc/init.d/S99spoolup start
```

**For Generic Linux:**
```bash
sudo systemctl start spoolup
sudo systemctl enable spoolup  # Auto-start on boot
```

### Step 6: Verify It's Working

```bash
# Check status
/usr/data/spoolup/status.sh

# Or view logs
tail -f /var/log/spoolup.log
```

## 🖥️ Installation on PC/Mac (Alternative)

If you prefer to run SpoolUp on your computer instead of the printer:

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

**Note:** When running on PC, update `config.json` to point to your printer's IP:
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
├── requirements.txt           # Core runtime dependencies (printer)
├── requirements-auth.txt      # Auth dependencies (PC/Mac only)
├── README.md                  # This file
│
├── spoolup/                   # Runtime package (runs on printer)
│   ├── __init__.py
│   ├── __main__.py
│   └── main.py               # Core application (NO auth flow)
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

## 🐛 Troubleshooting

### "Token file not found"

You need to authenticate on your PC/Mac first:
```bash
python -m spoolup_auth --client-secrets client_secrets.json
scp youtube_token.json root@<printer_ip>:/usr/data/spoolup/
```

### "Credentials are invalid or expired"

Re-authenticate on your PC/Mac:
```bash
python -m spoolup_auth --client-secrets client_secrets.json
scp youtube_token.json root@<printer_ip>:/usr/data/spoolup/
```

Then restart SpoolUp on the printer.

### FFmpeg not found

Install FFmpeg on your printer:
```bash
# K1 with Entware
opkg install ffmpeg

# Generic Linux
sudo apt-get install ffmpeg
```

### Service won't start

Check the logs:
```bash
tail -n 50 /var/log/spoolup.log
```

Verify the token file exists:
```bash
ls -la /usr/data/spoolup/youtube_token.json
```

## 🔄 Updating SpoolUp

To update SpoolUp to the latest version:

```bash
# SSH into your printer
ssh root@<printer_ip>

# Go to the SpoolUp directory
cd /usr/data/spoolup

# Pull latest changes
git pull

# Re-run the installer
sh install.sh

# Restart the service
/etc/init.d/S99spoolup restart
```

## 🗑️ Uninstalling

```bash
# Stop the service
/etc/init.d/S99spoolup stop  # or: systemctl stop spoolup

# Remove service files
rm -f /etc/init.d/S99spoolup
rm -f /etc/systemd/system/spoolup.service

# Remove installation directory
rm -rf /usr/data/spoolup
rm -rf ~/spoolup-env
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
