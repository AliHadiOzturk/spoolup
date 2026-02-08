#!/bin/sh
#
# SpoolUp Installation Script for Creality K1 Series (K1, K1 Max, K1C)
# 
# This script installs SpoolUp as a systemd service on rooted K1 printers
# Follows patterns from Creality Helper Script
#
# Usage:
#   1. Copy this script to your K1: scp install_k1.sh root@<printer_ip>:/tmp/
#   2. SSH into your K1: ssh root@<printer_ip>
#   3. Run: sh /tmp/install_k1.sh
#
# This version has SpoolUp embedded - no download needed!

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/usr/data/printer_data/config/spoolup"
SERVICE_NAME="spoolup"
LOG_FILE="/var/log/spoolup-install.log"

# Logging function
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}ℹ $1${NC}" | tee -a "$LOG_FILE"
}

echo ""
echo "========================================"
echo "  SpoolUp Installer for Creality K1"
echo "========================================"
echo ""

# Check if running on K1
if [ ! -d "/usr/data" ]; then
    error "This script is designed for Creality K1 series printers."
    error "Directory /usr/data not found. Are you sure this is a K1?"
    exit 1
fi

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root"
    exit 1
fi

success "Detected Creality K1 series printer"

# Determine K1 model
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')
    info "Printer model: $MODEL"
fi

# Step 1: Install dependencies
log ""
log "📦 Step 1: Installing dependencies..."

# Check if Entware is installed (common on modded K1)
if command -v opkg &> /dev/null; then
    info "Entware detected, updating packages..."
    opkg update >> "$LOG_FILE" 2>&1 || warning "Could not update Entware packages"
    
    # Install Python3 if not present
    if ! command -v python3 &> /dev/null; then
        info "Installing Python3..."
        opkg install python3 python3-pip >> "$LOG_FILE" 2>&1
    fi
    
    # Install FFmpeg if not present
    if ! command -v ffmpeg &> /dev/null; then
        info "Installing FFmpeg..."
        opkg install ffmpeg >> "$LOG_FILE" 2>&1
    fi
else
    warning "Entware not detected. Assuming dependencies are already installed."
fi

# Verify Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    success "Python version: $PYTHON_VERSION"
else
    error "Python3 not found. Please install Python3 first."
    exit 1
fi

# Verify FFmpeg
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version | head -n1 | cut -d' ' -f3)
    success "FFmpeg version: $FFMPEG_VERSION"
else
    error "FFmpeg not found. Please install FFmpeg first."
    exit 1
fi

# Step 2: Create installation directory
log ""
log "📁 Step 2: Creating installation directory..."

mkdir -p "$INSTALL_DIR"
success "Created: $INSTALL_DIR"

# Step 3: Extract SpoolUp from embedded bundle
log ""
log "⬇️  Step 3: Extracting SpoolUp..."
info "Extracting embedded SpoolUp bundle..."

# Extract the embedded tarball from this script
cd /tmp
sed -n '/^__SPOOLUP_BUNDLE__$/,/^__END_SPOOLUP_BUNDLE__$/p' "$0" | sed '1d;$d' | base64 -d > spoolup-bundle.tar.gz

if [ ! -f spoolup-bundle.tar.gz ] || [ ! -s spoolup-bundle.tar.gz ]; then
    error "Failed to extract SpoolUp bundle"
    exit 1
fi

# Extract to install directory
tar -xzf spoolup-bundle.tar.gz -C "$INSTALL_DIR/"
rm -f spoolup-bundle.tar.gz
success "Files installed to $INSTALL_DIR"

# Step 4: Install Python dependencies
log ""
log "🐍 Step 4: Installing Python dependencies..."

cd "$INSTALL_DIR"
python3 -m pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
success "Python dependencies installed"

# Step 5: Create configuration
log ""
log "⚙️  Step 5: Creating configuration..."

if [ ! -f "$INSTALL_DIR/config.json" ]; then
    # Detect timelapse directory (common locations on K1)
    if [ -d "/usr/data/printer_data/timelapse" ]; then
        TIMELAPSE_DIR="/usr/data/printer_data/timelapse"
    else
        TIMELAPSE_DIR="/usr/data/printer_data/timelapse"
        mkdir -p "$TIMELAPSE_DIR"
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
    success "Configuration created: $INSTALL_DIR/config.json"
else
    warning "Configuration already exists, skipping creation"
fi

# Step 6: Create service
log ""
log "🔧 Step 6: Creating service..."

# Check which init system is available
if [ -d "/etc/systemd/system" ]; then
    # Systemd available
    cat > /etc/systemd/system/${SERVICE_NAME}.service << 'EOF'
[Unit]
Description=SpoolUp - YouTube Streamer for 3D Prints
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/usr/data/printer_data/config/spoolup
ExecStart=/usr/bin/python3 /usr/data/printer_data/config/spoolup/spoolup.py -c /usr/data/printer_data/config/spoolup/config.json
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    INIT_TYPE="systemd"
    success "Systemd service created: ${SERVICE_NAME}.service"
elif [ -d "/etc/init.d" ]; then
    # OpenWrt/Buildroot init.d
    cat > /etc/init.d/S99${SERVICE_NAME} << 'EOF'
#!/bin/sh
# SpoolUp service script for K1

start() {
    echo "Starting SpoolUp..."
    cd /usr/data/printer_data/config/spoolup
    /usr/bin/python3 spoolup.py -c /usr/data/printer_data/config/spoolup/config.json > /var/log/spoolup.log 2>&1 &
    echo $! > /var/run/spoolup.pid
}

stop() {
    echo "Stopping SpoolUp..."
    if [ -f /var/run/spoolup.pid ]; then
        kill $(cat /var/run/spoolup.pid) 2>/dev/null
        rm -f /var/run/spoolup.pid
    fi
}

restart() {
    stop
    sleep 2
    start
}

status() {
    if [ -f /var/run/spoolup.pid ]; then
        if kill -0 $(cat /var/run/spoolup.pid) 2>/dev/null; then
            echo "SpoolUp is running"
        else
            echo "SpoolUp is not running (stale pid file)"
        fi
    else
        echo "SpoolUp is not running"
    fi
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) restart ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
EOF
    chmod +x /etc/init.d/S99${SERVICE_NAME}
    INIT_TYPE="initd"
    success "Init.d service created: S99${SERVICE_NAME}"
else
    warning "Unknown init system. Service will not be auto-started."
    INIT_TYPE="none"
fi

# Step 7: Create log file
log ""
log "📝 Step 7: Setting up logging..."

touch /var/log/spoolup.log
chmod 644 /var/log/spoolup.log
success "Log file created: /var/log/spoolup.log"

# Step 8: Create helper scripts
log ""
log "🛠️  Step 8: Creating helper scripts..."

# Create status script
cat > "$INSTALL_DIR/status.sh" << EOF
#!/bin/sh
# SpoolUp Status Checker

echo "========================================"
echo "  SpoolUp Service Status"
echo "========================================"
echo ""

# Check if service is running
if [ "$INIT_TYPE" = "systemd" ]; then
    if systemctl is-active --quiet spoolup 2>/dev/null; then
        echo "✓ Service Status: RUNNING"
    else
        echo "✗ Service Status: STOPPED"
    fi
elif [ "$INIT_TYPE" = "initd" ]; then
    /etc/init.d/S99${SERVICE_NAME} status
else
    echo "? Service Status: UNKNOWN (manual start required)"
fi

echo ""
echo "Recent logs (last 20 lines):"
echo "----------------------------------------"
tail -n 20 /var/log/spoolup.log 2>/dev/null || echo "No logs found"

echo ""
echo "========================================"
echo ""
echo "Useful commands:"
if [ "$INIT_TYPE" = "systemd" ]; then
    echo "  Start:   systemctl start spoolup"
    echo "  Stop:    systemctl stop spoolup"
    echo "  Restart: systemctl restart spoolup"
elif [ "$INIT_TYPE" = "initd" ]; then
    echo "  Start:   /etc/init.d/S99${SERVICE_NAME} start"
    echo "  Stop:    /etc/init.d/S99${SERVICE_NAME} stop"
    echo "  Restart: /etc/init.d/S99${SERVICE_NAME} restart"
fi
echo "  Logs:    tail -f /var/log/spoolup.log"
echo ""
EOF
chmod +x "$INSTALL_DIR/status.sh"

# Create authentication helper script
cat > "$INSTALL_DIR/authenticate.sh" << 'EOF'
#!/bin/sh
# SpoolUp Authentication Helper
# This script helps you authenticate with YouTube on a headless K1

echo ""
echo "========================================"
echo "  SpoolUp YouTube Authentication"
echo "========================================"
echo ""
echo "Since the K1 doesn't have a browser,"
echo "you have TWO options for authentication:"
echo ""
echo "OPTION 1: Authenticate on your PC (Recommended)"
echo "----------------------------------------"
echo "1. On your PC/Mac, download SpoolUp:"
echo "   git clone https://github.com/AliHadiOzturk/spoolup.git"
echo "   cd spoolup"
echo "   pip install -r requirements.txt"
echo ""
echo "2. Copy your client_secrets.json to the PC"
echo ""
echo "3. Authenticate on the PC:"
echo "   python3 spoolup.py --auth-only"
echo ""
echo "4. Copy the generated token to your K1:"
echo "   scp youtube_token.json root@<printer_ip>:/usr/data/printer_data/config/spoolup/"
echo ""
echo "OPTION 2: Headless Authentication on K1"
echo "----------------------------------------"
echo "1. Copy your client_secrets.json to:"
echo "   /usr/data/printer_data/config/spoolup/client_secrets.json"
echo ""
echo "2. Run authentication on K1:"
echo "   cd /usr/data/printer_data/config/spoolup"
echo "   python3 spoolup.py --auth-only --headless"
echo ""
echo "3. The script will display a URL. Copy this URL to your PC's browser."
echo ""
echo "4. Authorize SpoolUp and copy the authorization code."
echo ""
echo "5. Paste the code back into the SSH session."
echo ""
echo "========================================"
EOF
chmod +x "$INSTALL_DIR/authenticate.sh"

success "Helper scripts created"

# Installation complete
echo ""
echo "========================================"
echo "  ✅ Installation Complete!"
echo "========================================"
echo ""
echo "📍 Installation directory: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Get YouTube API credentials:"
echo "   - Go to https://console.cloud.google.com/"
echo "   - Create a project → Enable YouTube Data API v3"
echo "   - Create OAuth credentials (Desktop app)"
echo "   - Download client_secrets.json"
echo ""
echo "2️⃣  Copy client_secrets.json to your K1:"
echo "   scp client_secrets.json root@<printer_ip>:$INSTALL_DIR/"
echo ""
echo "3️⃣  Authenticate with YouTube:"
echo "   Run: $INSTALL_DIR/authenticate.sh"
echo "   (for authentication options)"
echo ""
echo "4️⃣  Start the service:"
if [ "$INIT_TYPE" = "systemd" ]; then
    echo "   systemctl start spoolup"
    echo ""
    echo "5️⃣  Enable auto-start on boot:"
    echo "   systemctl enable spoolup"
elif [ "$INIT_TYPE" = "initd" ]; then
    echo "   /etc/init.d/S99${SERVICE_NAME} start"
    echo ""
    echo "5️⃣  Enable auto-start on boot:"
    echo "   The service will start automatically on boot (S99 prefix)"
else
    echo "   cd $INSTALL_DIR && python3 spoolup.py"
    echo ""
    echo "5️⃣  Enable auto-start on boot:"
    echo "   Manual start required - add to /etc/init.d/ scripts"
fi
echo ""
echo "📊 Check status:"
echo "   $INSTALL_DIR/status.sh"
echo ""
echo "📖 View logs:"
echo "   tail -f /var/log/spoolup.log"
echo ""
echo "========================================"
echo ""

exit 0

# Embedded SpoolUp bundle (base64 encoded tarball)
# DO NOT EDIT BELOW THIS LINE
__SPOOLUP_BUNDLE__
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

__END_SPOOLUP_BUNDLE__
