#!/bin/bash
#
# SpoolUp Installation Script for Creality K1 Series (K1, K1 Max, K1C)
# 
# This script installs SpoolUp as a systemd service on rooted K1 printers
# Follows patterns from Creality Helper Script
#
# Usage:
#   1. Copy this script to your K1: scp install_k1.sh root@<printer_ip>:/tmp/
#   2. SSH into your K1: ssh root@<printer_ip>
#   3. Run: bash /tmp/install_k1.sh
#

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

# Step 3: Download SpoolUp
log ""
log "⬇️  Step 3: Downloading SpoolUp..."

info "Downloading latest version from GitHub..."
cd /tmp

# Download the repository
# Prefer wget on K1 since curl often lacks SSL support
if command -v wget &> /dev/null; then
    wget -O spoolup.tar.gz "https://github.com/AliHadiOzturk/spoolup/archive/refs/heads/main.tar.gz" 2>&1 | tee -a "$LOG_FILE"
elif command -v curl &> /dev/null; then
    curl -L -o spoolup.tar.gz "https://github.com/AliHadiOzturk/spoolup/archive/refs/heads/main.tar.gz" 2>&1 | tee -a "$LOG_FILE"
else
    error "Neither wget nor curl found. Cannot download SpoolUp."
    exit 1
fi

# Extract and copy files
if [ -f spoolup.tar.gz ]; then
    tar -xzf spoolup.tar.gz
    cp -r spoolup-main/* "$INSTALL_DIR/"
    rm -rf spoolup.tar.gz spoolup-main
    success "Files installed to $INSTALL_DIR"
else
    error "Failed to download SpoolUp"
    exit 1
fi

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

# Step 6: Create systemd service
log ""
log "🔧 Step 6: Creating systemd service..."

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

systemctl daemon-reload
success "Systemd service created: ${SERVICE_NAME}.service"

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
cat > "$INSTALL_DIR/status.sh" << 'EOF'
#!/bin/bash
# SpoolUp Status Checker

echo "========================================"
echo "  SpoolUp Service Status"
echo "========================================"
echo ""

# Check if service is running
if systemctl is-active --quiet spoolup; then
    echo "✓ Service Status: RUNNING"
else
    echo "✗ Service Status: STOPPED"
fi

echo ""
echo "Recent logs (last 20 lines):"
echo "----------------------------------------"
tail -n 20 /var/log/spoolup.log 2>/dev/null || echo "No logs found"

echo ""
echo "========================================"
echo ""
echo "Useful commands:"
echo "  Start:   systemctl start spoolup"
echo "  Stop:    systemctl stop spoolup"
echo "  Restart: systemctl restart spoolup"
echo "  Logs:    tail -f /var/log/spoolup.log"
echo ""
EOF
chmod +x "$INSTALL_DIR/status.sh"

# Create authentication helper script
cat > "$INSTALL_DIR/authenticate.sh" << 'EOF'
#!/bin/bash
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
echo "   systemctl start spoolup"
echo ""
echo "5️⃣  Enable auto-start on boot:"
echo "   systemctl enable spoolup"
echo ""
echo "📊 Check status:"
echo "   $INSTALL_DIR/status.sh"
echo ""
echo "📖 View logs:"
echo "   tail -f /var/log/spoolup.log"
echo ""
echo "========================================"
echo ""
