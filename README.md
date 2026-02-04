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

## 📋 Requirements

- Python 3.7 or higher
- Klipper firmware with Moonraker API enabled
- FFmpeg installed on your system
- YouTube Data API v3 credentials
- A webcam configured with your Klipper setup

## 🚀 Quick Start

### 📍 Where to Install SpoolUp?

SpoolUp needs to run **on a machine that can access both your printer and the internet**. You have two main options:

#### Option A: Install ON Your Printer (Recommended)

**Best for:** Creality K1/K1 Max/K1C, Raspberry Pi setups, or any Linux-based printer with root access

- ✅ Always running (even when your PC is off)
- ✅ Direct access to printer's Moonraker API
- ✅ Can run as a system service
- ⚠️ Requires SSH access to the printer
- ⚠️ YouTube authentication needs special handling (no browser on printer)

**For K1 users:** Use the [K1 Installation Script](#️-creality-k1-installation) below

#### Option B: Install ON Your PC/Mac

**Best for:** Testing, development, or printers without SSH access

- ✅ Easier setup (you have a browser for authentication)
- ✅ Easier debugging and log viewing
- ⚠️ PC must stay on during prints
- ⚠️ PC must be on the same network as the printer

**Note:** If installing on PC, make sure your PC has a stable network connection to the printer throughout the print.

---

### 🖨️ Installation ON the Printer (K1/K1 Max/K1C)

See the [Creality K1 Installation](#️-creality-k1-installation) section below for the automated installer.

### 💻 Installation ON Your PC/Mac

#### 1. Clone the Repository

```bash
cd ~
git clone https://github.com/AliHadiOzturk/spoolup.git
cd spoolup
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

#### 4. Configure for Remote Printer

When running on your PC, you need to point SpoolUp to your printer's Moonraker API:

```json
{
  "moonraker_url": "http://192.168.1.100:7125",
  "webcam_url": "http://192.168.1.100:8080/?action=stream",
  "timelapse_dir": "/path/to/timelapse/on/printer",
  "client_secrets_file": "client_secrets.json",
  "token_file": "youtube_token.json",
  "stream_resolution": "1280x720",
  "stream_fps": 30,
  "stream_bitrate": "4000k"
}
```

**Note:** `timelapse_dir` should be a path accessible from the PC (e.g., network share) if you want timelapse upload. If not, disable timelapse upload and only use live streaming.

---

### 🔐 YouTube API Setup (Both Options)

#### 5. Set Up YouTube API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable **YouTube Data API v3**:
   - Go to "Library" in the left menu
   - Search for "YouTube Data API v3"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "Credentials" in the left menu
   - Click "Create Credentials" → "OAuth client ID"
   - Choose "Desktop app" as the application type
   - Give it a name (e.g., "SpoolUp")
   - Click "Create"
5. Download the client secrets:
    - Click the download icon next to your credentials
    - Save the file as `client_secrets.json` in the spoolup directory

---

### ⚙️ Configuration

Create a sample configuration:

```bash
python spoolup.py --create-config
```

Edit `config.json` with your settings:

```json
{
  "moonraker_url": "http://localhost:7125",
  "webcam_url": "http://localhost:8080/?action=stream",
  "timelapse_dir": "/home/user/printer_data/timelapse",
  "client_secrets_file": "client_secrets.json",
  "token_file": "youtube_token.json",
  "stream_resolution": "1280x720",
  "stream_fps": 30,
  "stream_bitrate": "4000k",
  "stream_privacy": "unlisted",
  "youtube_category_id": "28",
  "video_privacy": "private",
  "enable_live_stream": true,
  "enable_timelapse_upload": true
}
```

---

### 🔑 Authentication

#### If Installing ON Your PC/Mac:

Run the authentication flow (opens browser automatically):

```bash
python spoolup.py --auth-only
```

#### If Installing ON Your Printer (K1):

Since the printer has no browser, you have two options:

**Option 1: Authenticate on PC, Copy Token to Printer (Recommended)**

1. On your PC/Mac (same one you downloaded SpoolUp to):
   ```bash
   python3 spoolup.py --auth-only
   ```
   This opens a browser and creates `youtube_token.json`

2. Copy the token to your printer:
   ```bash
   scp youtube_token.json root@<printer_ip>:/usr/data/printer_data/config/spoolup/
   ```

**Option 2: Headless Authentication on Printer**

1. SSH to your printer and run:
   ```bash
   python3 spoolup.py --auth-only --headless
   ```

2. Copy the displayed URL to your PC's browser

3. Authorize and copy the authorization code

4. Paste the code back in the SSH session

---

### 🧪 Test Your Setup

Run the verification script to check everything is configured correctly:

```bash
python test_setup.py
```

---

### ▶️ Run SpoolUp

```bash
# Run manually to test
python spoolup.py

# Or with a custom config file
python spoolup.py -c /path/to/config.json
```

## 🖨️ Creality K1 Installation

For **Creality K1, K1 Max, and K1C** printers with rooted firmware, use the automated installer:

### Quick Install

```bash
# 1. Download and run the installer on your K1
ssh root@<your_printer_ip>
curl -fsSL https://raw.githubusercontent.com/AliHadiOzturk/spoolup/main/install_k1.sh | bash

# Or manually:
# scp install_k1.sh root@<your_printer_ip>:/tmp/
# ssh root@<your_printer_ip>
# bash /tmp/install_k1.sh
```

### K1-Specific Configuration

The installer automatically configures SpoolUp for K1 paths:
- **Installation directory**: `/usr/data/printer_data/config/spoolup/`
- **Timelapse directory**: `/usr/data/printer_data/timelapse/`
- **Service**: Runs as systemd service under root
- **Logs**: `/var/log/spoolup.log`

### YouTube Authentication on K1

The K1 doesn't have a browser, so follow the **"If Installing ON Your Printer"** instructions in the [Authentication section](#-authentication) above.

**Quick Summary:**

1. **Get YouTube API credentials** from Google Cloud Console
2. **Copy `client_secrets.json`** to your K1:
   ```bash
   scp client_secrets.json root@<printer_ip>:/usr/data/printer_data/config/spoolup/
   ```
3. **Authenticate using your PC** (recommended):
   ```bash
   # On your PC
   python3 spoolup.py --auth-only
   scp youtube_token.json root@<printer_ip>:/usr/data/printer_data/config/spoolup/
   ```

### Managing the Service on K1

```bash
# Start SpoolUp
systemctl start spoolup

# Stop SpoolUp
systemctl stop spoolup

# Restart SpoolUp
systemctl restart spoolup

# Check status
systemctl status spoolup
/usr/data/printer_data/config/spoolup/status.sh

# Enable auto-start on boot
systemctl enable spoolup

# View logs
tail -f /var/log/spoolup.log
```

## 🔧 Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `moonraker_url` | URL of your Moonraker instance | `http://localhost:7125` |
| `webcam_url` | URL of your MJPEG webcam stream | `http://localhost:8080/?action=stream` |
| `timelapse_dir` | Directory where timelapse videos are saved | `/home/user/printer_data/timelapse` |
| `client_secrets_file` | Path to Google OAuth client secrets | `client_secrets.json` |
| `token_file` | Path to save YouTube authentication token | `youtube_token.json` |
| `stream_resolution` | Live stream resolution (e.g., 1280x720) | `1280x720` |
| `stream_fps` | Live stream frame rate | `30` |
| `stream_bitrate` | Live stream video bitrate | `4000k` |
| `stream_privacy` | Live stream privacy (public/unlisted/private) | `unlisted` |
| `video_privacy` | Uploaded timelapse privacy (public/unlisted/private) | `private` |
| `youtube_category_id` | YouTube category ID for uploads | `28` (Science & Technology) |
| `enable_live_stream` | Enable live streaming feature | `true` |
| `enable_timelapse_upload` | Enable timelapse upload feature | `true` |

## 🖥️ Run as a Service

To run SpoolUp automatically on boot:

```bash
# Copy the service file
sudo cp spoolup.service /etc/systemd/system/

# Edit the service file to match your setup (if needed)
sudo nano /etc/systemd/system/spoolup.service

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable spoolup.service
sudo systemctl start spoolup.service

# Check status
sudo systemctl status spoolup.service

# View logs
sudo tail -f /var/log/spoolup.log
```

## 📖 Usage

Once SpoolUp is running:

1. **Start a print** - SpoolUp will automatically create a YouTube Live stream and start streaming your webcam feed
2. **Check the logs** - Watch the console output or check `/tmp/spoolup.log`
3. **View the live stream** - The YouTube Live URL will be logged when the stream starts
4. **Complete the print** - The live stream will automatically end and the timelapse will be uploaded as a draft
5. **Publish the timelapse** - Go to YouTube Studio to edit the description and publish the video

### Command Line Options

```bash
python spoolup.py [OPTIONS]

Options:
  -c, --config PATH       Path to configuration file (default: config.json)
  --create-config         Create a sample configuration file
  --auth-only             Only authenticate with YouTube and exit
  --headless              Use headless authentication (for machines without browser)
  -h, --help              Show help message
```

**Authentication Options:**

- **`--auth-only`**: Run authentication flow and exit (useful for setup)
- **`--headless`**: Use console-based authentication instead of browser (for headless machines like K1)

Common authentication scenarios:

```bash
# Desktop with browser (opens browser automatically)
python spoolup.py --auth-only

# Headless machine (shows URL to open on another device)
python spoolup.py --auth-only --headless

# Run the service
python spoolup.py
```

## 🐛 Troubleshooting

### Setup Test Failures

Run `python test_setup.py` to diagnose issues:

```bash
# Test Python version
python --version  # Should be 3.7+

# Test imports
python -c "import requests, websocket, googleapiclient.discovery"

# Test FFmpeg
ffmpeg -version
```

### FFmpeg Not Found

Install FFmpeg:

```bash
# For K1 Max (Entware)
opkg install ffmpeg

# Verify installation
which ffmpeg
ffmpeg -version
```

### Authentication Issues

If authentication fails:

1. Delete the `youtube_token.json` file
2. Re-run authentication: `python spoolup.py --auth-only`
3. Ensure your `client_secrets.json` is valid and placed in the correct directory

**For headless machines (K1, servers without browser):**

If you see an error about "cannot open browser" or "webbrowser" module:

1. **Use headless mode** (requires copy-pasting the authorization code):
   ```bash
   python spoolup.py --auth-only --headless
   ```

2. **Or authenticate on a different machine** (recommended for K1):
   - Run authentication on your PC/Mac: `python spoolup.py --auth-only`
   - Copy the generated `youtube_token.json` to your K1:
     ```bash
     scp youtube_token.json root@<k1_ip>:/usr/data/printer_data/config/spoolup/
     ```

### Stream Not Starting

Check the FFmpeg command:

1. Enable debug logging by setting the log level in the script
2. Check `/tmp/spoolup.log` for FFmpeg error messages
3. Verify your webcam URL is accessible: `curl http://localhost:8080/?action=stream`

### Timelapse Not Found

Ensure the timelapse directory path is correct:

```bash
# Check if the directory exists
ls -la /path/to/timelapse/dir

# Check Moonraker timelapse settings
curl http://localhost:7125/server/timelapse/settings
```

### WebSocket Connection Issues

If SpoolUp can't connect to Moonraker:

1. Verify Moonraker is running: `systemctl status moonraker`
2. Check the Moonraker URL in your config
3. Ensure the URL is accessible: `curl http://localhost:7125/printer/info`

## 🏗️ Architecture

SpoolUp consists of several key components:

- **SpoolUp** - Main application class that orchestrates everything
- **MoonrakerClient** - WebSocket client for real-time printer status
- **YouTubeStreamer** - Handles YouTube Live stream creation and FFmpeg streaming
- **YouTubeUploader** - Manages timelapse video uploads
- **Config** - Configuration management

The application runs as a long-lived service, monitoring your printer via WebSocket and automatically responding to print state changes.

## 🔒 Security Notes

- Keep your `client_secrets.json` and `youtube_token.json` secure - they contain OAuth credentials
- Don't commit these files to public repositories
- Consider setting uploaded videos to "private" by default (configurable in settings)
- The default log file location is `/tmp/spoolup.log` (cleared on reboot) or `/var/log/spoolup.log` (persistent)

## 📁 File Structure

```
spoolup/
├── spoolup.py              # Main application
├── test_setup.py           # Setup verification script
├── requirements.txt        # Python dependencies
├── install_k1.sh           # K1-specific installation script
├── install_generic.sh      # Generic Linux installation script
├── spoolup.service         # Systemd service file (K1-optimized)
├── config.json             # Your configuration (not in repo)
├── config.json.sample      # Sample configuration
├── client_secrets.json     # YouTube API credentials (you provide)
├── youtube_token.json      # Generated after authentication
├── README.md               # This file
└── AGENTS.md               # Guidelines for AI agents
```

## 🛠️ Development

See `AGENTS.md` for coding guidelines if you're contributing to the project.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License - Feel free to modify and distribute. See LICENSE file for details.

## 📞 Support

For issues, questions, or contributions:
- Check the troubleshooting section above
- Review the logs at `/tmp/spoolup.log`
- Open an issue on the repository

---

**Happy Printing! 🎉**

*SpoolUp - Because your prints deserve an audience.*
