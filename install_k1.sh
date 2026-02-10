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
INSTALL_DIR="/usr/data/spoolup"
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

# Detect which Python to use (prefer Entware over system)
if [ -x "/opt/bin/python3" ]; then
    PYTHON="/opt/bin/python3"
    PIP="/opt/bin/python3 -m pip"
    info "Using Entware Python: $PYTHON"
elif [ -x "/usr/bin/python3" ]; then
    PYTHON="/usr/bin/python3"
    PIP="/usr/bin/python3 -m pip"
    info "Using system Python: $PYTHON"
else
    PYTHON="python3"
    PIP="python3 -m pip"
    warning "Using default Python from PATH"
fi


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
if command -v "$PYTHON" &> /dev/null; then
    PYTHON_VERSION=$($PYTHON --version 2>&1 | cut -d' ' -f2)
    success "Python version: $PYTHON_VERSION"
else
    error "Python3 not found. Please install Python3 first."
    exit 1
fi

# Verify pip is available
if ! $PIP --version &> /dev/null; then
    error "pip is not installed for Python3"
    info "Attempting to install pip..."
    
    # Try to install pip via Entware if available
    if command -v opkg &> /dev/null; then
        opkg install python3-pip >> "$LOG_FILE" 2>&1
    fi
    
    # Check again if pip is now available
    if ! $PIP --version &> /dev/null; then
        error "Failed to install pip. Please install python3-pip manually:"
        error "  opkg install python3-pip"
        exit 1
    fi
fi
success "pip is available"

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
# Check if script is being run from a file (not piped)
if [ ! -f "$0" ]; then
    error "This script must be saved to a file before running."
    error "Please run: wget -O /tmp/install_k1.sh https://raw.githubusercontent.com/AliHadiOzturk/spoolup/main/install_k1.sh"
    error "Then: sh /tmp/install_k1.sh"
    exit 1
fi

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

# Install dependencies using detected Python
# Use --prefer-binary to avoid building from source on embedded systems
info "Installing dependencies (this may take a while)..."
if ! $PIP install -r requirements.txt --prefer-binary 2>&1 | tee -a "$LOG_FILE"; then
    warning "Installation with Entware Python failed, trying system Python..."
    
    if [ -x "/usr/bin/python3" ]; then
        info "Attempting installation with system Python..."
        /usr/bin/python3 -m pip install -r requirements.txt --prefer-binary 2>&1 | tee -a "$LOG_FILE"
        warning "Switching to system Python (/usr/bin/python3) for service..."
        PYTHON="/usr/bin/python3"
    else
        error "Failed to install Python dependencies with both Python versions"
        exit 1
    fi
fi

# Verify key imports work with detected Python
if ! $PYTHON -c "import requests, websocket, googleapiclient.discovery" 2>/dev/null; then
    error "Python dependencies installed but imports failed"
    error "This may indicate a permission or path issue"
    exit 1
fi

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
WorkingDirectory=/usr/data/spoolup
ExecStart=$PYTHON /usr/data/spoolup/spoolup.py -c /usr/data/spoolup/config.json
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
    cat > /etc/init.d/S99${SERVICE_NAME} << EOF
#!/bin/sh
# SpoolUp service script for K1

start() {
    echo "Starting SpoolUp..."
    cd /usr/data/spoolup
    $PYTHON spoolup.py -c /usr/data/spoolup/config.json > /var/log/spoolup.log 2>&1 &
    echo \$! > /var/run/spoolup.pid
}

stop() {
    echo "Stopping SpoolUp..."
    if [ -f /var/run/spoolup.pid ]; then
        kill \$(cat /var/run/spoolup.pid) 2>/dev/null
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
        if kill -0 \$(cat /var/run/spoolup.pid) 2>/dev/null; then
            echo "SpoolUp is running"
        else
            echo "SpoolUp is not running (stale pid file)"
        fi
    else
        echo "SpoolUp is not running"
    fi
}

case "\$1" in
    start) start ;;
    stop) stop ;;
    restart) restart ;;
    status) status ;;
    *) echo "Usage: \$0 {start|stop|restart|status}"; exit 1 ;;
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
echo "   scp youtube_token.json root@<printer_ip>:/usr/data/spoolup/"
echo ""
echo "OPTION 2: Headless Authentication on K1"
echo "----------------------------------------"
echo "1. Copy your client_secrets.json to:"
echo "   /usr/data/spoolup/client_secrets.json"
echo ""
echo "2. Run authentication on K1:"
echo "   cd /usr/data/spoolup"
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
