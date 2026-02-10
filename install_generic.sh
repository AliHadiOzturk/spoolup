#!/bin/bash
#
# SpoolUp Installation Script
# For Creality K1 Max and other Klipper-based 3D printers
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/home/user/printer_data/config/spoolup}"
LOG_FILE="/tmp/klipper-youtube-install.log"

echo "========================================"
echo "SpoolUp Installer"
echo "========================================"
echo ""

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    log "⚠️  This script needs to be run as root for system-wide installation"
    log "   Run with: sudo $0"
    exit 1
fi

log "📦 Starting installation..."

# Detect printer model and adjust paths
if [ -d "/usr/data" ]; then
    # K1 Max with Creality OS
    log "🔍 Detected: Creality K1 Max (Creality OS)"
    INSTALL_DIR="/usr/data/spoolup"
    USER_HOME="/root"
    PYTHON_CMD="python3"
elif [ -d "/home/pi" ]; then
    # Raspberry Pi (likely with Mainsail/Fluidd)
    log "🔍 Detected: Raspberry Pi setup"
    INSTALL_DIR="/home/pi/printer_data/config/spoolup"
    USER_HOME="/home/pi"
    PYTHON_CMD="python3"
else
    log "🔍 Using default paths"
    INSTALL_DIR="/home/user/printer_data/config/spoolup"
    USER_HOME="/root"
    PYTHON_CMD="python3"
fi

# Check Python version
log "🐍 Checking Python installation..."
if ! command -v $PYTHON_CMD &> /dev/null; then
    log "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
log "   Found Python version: $PYTHON_VERSION"

# Check FFmpeg
log "🎥 Checking FFmpeg installation..."
if ! command -v ffmpeg &> /dev/null; then
    log "⚠️  FFmpeg not found. Attempting to install..."
    
    if command -v apt-get &> /dev/null; then
        apt-get update && apt-get install -y ffmpeg
    elif command -v opkg &> /dev/null; then
        opkg update && opkg install ffmpeg
    else
        log "❌ Could not install FFmpeg automatically. Please install FFmpeg manually."
        exit 1
    fi
else
    log "   FFmpeg is already installed: $(ffmpeg -version | head -n1)"
fi

# Create installation directory
log "📁 Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy files
log "📋 Copying files..."
cp -r "$SCRIPT_DIR"/*.py "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR"/requirements.txt "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/README.md "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/*.service "$INSTALL_DIR/"

# Create config if it doesn't exist
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    log "⚙️  Creating default configuration..."
    
    # Find timelapse directory
    TIMELAPSE_DIR=""
    if [ -d "/usr/data/printer_data/timelapse" ]; then
        TIMELAPSE_DIR="/usr/data/printer_data/timelapse"
    elif [ -d "/home/pi/printer_data/timelapse" ]; then
        TIMELAPSE_DIR="/home/pi/printer_data/timelapse"
    elif [ -d "/home/user/printer_data/timelapse" ]; then
        TIMELAPSE_DIR="/home/user/printer_data/timelapse"
    else
        TIMELAPSE_DIR="$USER_HOME/printer_data/timelapse"
    fi
    
    cat > "$INSTALL_DIR/config.json" << EOF
{
  "moonraker_url": "http://localhost:7125",
  "webcam_url": "http://localhost:8080/?action=stream",
  "timelapse_dir": "$TIMELAPSE_DIR",
  "client_secrets_file": "$INSTALL_DIR/client_secrets.json",
  "token_file": "$INSTALL_DIR/youtube_token.json",
  "stream_resolution": "1280x720",
  "stream_fps": 30,
  "stream_bitrate": "4000k",
  "stream_privacy": "unlisted",
  "youtube_category_id": "28",
  "video_privacy": "private",
  "enable_live_stream": true,
  "enable_timelapse_upload": true
}
EOF
fi

# Install Python dependencies
log "📥 Installing Python dependencies..."
cd "$INSTALL_DIR"
$PYTHON_CMD -m pip install -r requirements.txt --quiet

# Create systemd service
log "🔧 Setting up systemd service..."
SERVICE_FILE="/etc/systemd/system/spoolup.service"

if [ -d "/usr/data" ]; then
    # Creality OS specific service
    cat > "$SERVICE_FILE" << 'EOF'
[Unit]
Description=SpoolUp
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/usr/data/spoolup
ExecStart=/usr/bin/python3 /usr/data/spoolup/spoolup.py -c /usr/data/spoolup/config.json
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
EOF
else
    # Generic service
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=SpoolUp
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/spoolup.py -c $INSTALL_DIR/config.json
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
EOF
fi

# Reload systemd
systemctl daemon-reload

# Create log file
mkdir -p /var/log
touch /var/log/spoolup.log
chmod 644 /var/log/spoolup.log

echo ""
echo "========================================"
echo "✅ Installation Complete!"
echo "========================================"
echo ""
echo "📍 Installation directory: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo ""
echo "1. 📋 Get YouTube API credentials:"
echo "   - Go to https://console.cloud.google.com/"
echo "   - Create a new project"
echo "   - Enable YouTube Data API v3"
echo "   - Create OAuth 2.0 credentials (Desktop app)"
echo "   - Download and save as: $INSTALL_DIR/client_secrets.json"
echo ""
echo "2. 🔐 Authenticate with YouTube:"
echo "   cd $INSTALL_DIR"
echo "   python3 spoolup.py --auth-only"
echo ""
echo "3. ▶️  Start the service:"
echo "   systemctl start spoolup.service"
echo ""
echo "4. 📝 View logs:"
echo "   tail -f /var/log/spoolup.log"
echo ""
echo "5. 🔄 Enable auto-start on boot:"
echo "   systemctl enable spoolup.service"
echo ""
echo "📖 For more information, see: $INSTALL_DIR/README.md"
echo ""
