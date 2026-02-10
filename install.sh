#!/bin/sh

set -e

white='\033[0m'
red='\033[0;31m'
green='\033[0;32m'
yellow='\033[1;33m'
cyan='\033[0;36m'

top_line() {
    echo -e "${white}┌─────────────────────────────────────────────────────────────┐${white}"
}

bottom_line() {
    echo -e "${white}└─────────────────────────────────────────────────────────────┘${white}"
}

title() {
    local text="$1"
    local color="${2:-$white}"
    local padding=$(( (61 - ${#text}) / 2 ))
    printf "${white}│${color}%*s%s%*s${white}│\n" $padding "" "$text" $padding ""
}

inner_line() {
    echo -e "${white}├─────────────────────────────────────────────────────────────┤${white}"
}

hr() {
    echo -e "${white}│                                                             │${white}"
}

info_msg() {
    echo -e "${white}Info: $1${white}"
}

ok_msg() {
    echo -e "${green}✓ $1${white}"
}

error_msg() {
    echo -e "${red}✗ $1${white}"
}

warning_msg() {
    echo -e "${yellow}⚠ $1${white}"
}

install_msg() {
    local component="$1"
    local yn_var="$2"
    echo -e "${white}│                                                             │${white}"
    echo -e "${white}│  Do you want to install ${cyan}${component}${white}?                             │${white}"
    echo -e "${white}│                                                             │${white}"
    echo -e "${white}│  [Y] Yes    [N] No                                          │${white}"
    echo -e "${white}│                                                             │${white}"
    echo -ne "${white}│  Choice: ${white}"
    read -r "${yn_var}"
}

REPO_URL="https://github.com/AliHadiOzturk/spoolup.git"
INSTALL_DIR=""
VENV_DIR=""

IS_K1_OS=0
IS_SONIC_PAD_OS=0
IS_K2_OS=0

 detect_os() {
    if grep -Fqs "ID=buildroot" /etc/os-release 2>/dev/null; then
        IS_K1_OS=1
        INSTALL_DIR="/usr/data/printer_data/config/spoolup"
        VENV_DIR="/usr/data/spoolup-env"
    elif grep -Fqs "sonic" /etc/openwrt_release 2>/dev/null; then
        IS_SONIC_PAD_OS=1
        INSTALL_DIR="/usr/share/spoolup"
        VENV_DIR="/usr/share/spoolup-env"
    elif grep -Fiqs "tina" /etc/openwrt_release 2>/dev/null && [ -f /usr/bin/webrtc ]; then
        IS_K2_OS=1
        INSTALL_DIR="/mnt/UDISK/spoolup"
        VENV_DIR="/mnt/UDISK/spoolup-env"
    else
        INSTALL_DIR="/opt/spoolup"
        VENV_DIR="/opt/spoolup-env"
    fi
}

print_banner() {
    top_line
    title 'SpoolUp' "$cyan"
    inner_line
    hr
    echo -e " │ ${cyan}Automatically stream your 3D prints to YouTube Live       ${white}│"
    echo -e " │ ${cyan}and upload timelapse videos when prints complete.          ${white}│"
    hr
    bottom_line
    echo
}

print_requirements() {
    echo -e "${white}Requirements:${white}"
    echo -e "  ${white}• Python 3.7+${white}"
    echo -e "  ${white}• FFmpeg${white}"
    echo -e "  ${white}• YouTube API credentials (client_secrets.json)${white}"
    echo
    echo -e "${white}Note: Authentication is done separately on your PC/Mac.${white}"
    echo -e "${white}      This installer only sets up the runtime.          ${white}"
    echo
}

check_requirements() {
    local missing=0
    
    info_msg "Checking requirements..."
    
    if ! command -v python3 >/dev/null 2>&1; then
        error_msg "Python 3 is not installed"
        missing=1
    else
        local py_version
        py_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        ok_msg "Python version: $py_version"
    fi
    
    if ! command -v ffmpeg >/dev/null 2>&1; then
        warning_msg "FFmpeg not found - will attempt to install"
    else
        ok_msg "FFmpeg found"
    fi
    
    if ! command -v git >/dev/null 2>&1; then
        error_msg "Git is not installed"
        missing=1
    else
        ok_msg "Git found"
    fi
    
    if [ $missing -eq 1 ]; then
        error_msg "Please install missing requirements and try again"
        exit 1
    fi
}

install_system_deps() {
    info_msg "Installing system dependencies..."
    
    if [ $IS_K1_OS -eq 1 ] || [ $IS_K2_OS -eq 1 ] || [ $IS_SONIC_PAD_OS -eq 1 ]; then
        if command -v opkg >/dev/null 2>&1; then
            opkg update || true
            opkg install python3 python3-pip ffmpeg || warning_msg "Some packages failed to install"
        fi
        pip3 install -q virtualenv || warning_msg "Failed to install virtualenv via pip"
    else
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv ffmpeg git
        elif command -v yum >/dev/null 2>&1; then
            sudo yum install -y python3 python3-pip ffmpeg git
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S --noconfirm python python-pip ffmpeg git
        fi
    fi
}

clone_repo() {
    if [ -d "$INSTALL_DIR" ]; then
        info_msg "SpoolUp directory exists, updating..."
        cd "$INSTALL_DIR"
        git fetch origin
        git reset --hard origin/main
    else
        info_msg "Cloning SpoolUp repository..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

setup_venv() {
    info_msg "Setting up Python virtual environment..."
    
    if [ ! -d "$VENV_DIR" ]; then
        if [ $IS_K1_OS -eq 1 ] || [ $IS_K2_OS -eq 1 ]; then
            if [ -f /opt/bin/virtualenv ]; then
                /opt/bin/virtualenv -p /opt/bin/python3 --system-site-packages "$VENV_DIR"
            else
                python3 -m virtualenv -p /usr/bin/python3 --system-site-packages "$VENV_DIR"
            fi
        else
            python3 -m venv "$VENV_DIR"
        fi
    fi
    
    ok_msg "Virtual environment ready"
}

install_python_deps() {
    info_msg "Installing Python dependencies..."
    
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
    
    ok_msg "Python dependencies installed"
}

create_config() {
    local config_file="$INSTALL_DIR/config.json"
    
    if [ -f "$config_file" ]; then
        info_msg "Configuration file exists, skipping creation"
        return
    fi
    
    info_msg "Creating configuration file..."
    
    local timelapse_dir
    if [ $IS_K1_OS -eq 1 ] || [ $IS_K2_OS -eq 1 ]; then
        timelapse_dir="/usr/data/printer_data/timelapse"
    elif [ $IS_SONIC_PAD_OS -eq 1 ]; then
        timelapse_dir="/usr/share/printer_data/timelapse"
    else
        timelapse_dir="/var/lib/moonraker/timelapse"
    fi
    
    cat > "$config_file" << EOF
{
  "moonraker_url": "http://localhost:7125",
  "webcam_url": "http://localhost:8080/?action=stream",
  "timelapse_dir": "$timelapse_dir",
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
    
    ok_msg "Configuration created"
}

create_service() {
    info_msg "Creating service..."
    
    if [ -d /etc/systemd/system ] && [ $IS_K1_OS -eq 0 ] && [ $IS_K2_OS -eq 0 ] && [ $IS_SONIC_PAD_OS -eq 0 ]; then
        cat > /etc/systemd/system/spoolup.service << EOF
[Unit]
Description=SpoolUp - YouTube Streamer for 3D Prints
After=network-online.target moonraker.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python -m spoolup -c $INSTALL_DIR/config.json
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        ok_msg "Systemd service created"
        
    elif [ -d /etc/init.d ] || [ $IS_K1_OS -eq 1 ] || [ $IS_K2_OS -eq 1 ] || [ $IS_SONIC_PAD_OS -eq 1 ]; then
        cat > /etc/init.d/S99spoolup << EOF
#!/bin/sh
# SpoolUp service

cd $INSTALL_DIR

case "\$1" in
    start)
        echo "Starting SpoolUp..."
        $VENV_DIR/bin/python -m spoolup -c $INSTALL_DIR/config.json > /var/log/spoolup.log 2>&1 &
        echo \$! > /var/run/spoolup.pid
        ;;
    stop)
        echo "Stopping SpoolUp..."
        if [ -f /var/run/spoolup.pid ]; then
            kill \$(cat /var/run/spoolup.pid) 2>/dev/null
            rm -f /var/run/spoolup.pid
        fi
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        if [ -f /var/run/spoolup.pid ] && kill -0 \$(cat /var/run/spoolup.pid) 2>/dev/null; then
            echo "SpoolUp is running"
        else
            echo "SpoolUp is not running"
        fi
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF
        chmod +x /etc/init.d/S99spoolup
        ok_msg "Init.d service created"
    fi
}

print_next_steps() {
    echo
    top_line
    title 'Installation Complete!' "$green"
    inner_line
    hr
    echo -e " │ ${white}SpoolUp has been installed to:                              │${white}"
    echo -e " │ ${cyan}$INSTALL_DIR${white}"
    hr
    echo -e " │ ${yellow}Next Steps:${white}                                                 │${white}"
    hr
    echo -e " │ ${white}1. Authenticate on your PC/Mac:${white}                            │${white}"
    echo -e " │    ${cyan}pip install -r requirements-auth.txt${white}                    │${white}"
    echo -e " │    ${cyan}python -m spoolup_auth --client-secrets ...${white}             │${white}"
    hr
    echo -e " │ ${white}2. Copy token to printer:${white}                                  │${white}"
    echo -e " │    ${cyan}scp youtube_token.json root@<ip>:$INSTALL_DIR/${white}"
    hr
    echo -e " │ ${white}3. Start the service:${white}                                      │${white}"
    if [ -f /etc/systemd/system/spoolup.service ]; then
        echo -e " │    ${cyan}systemctl start spoolup${white}                                 │${white}"
    else
        echo -e " │    ${cyan}/etc/init.d/S99spoolup start${white}                           │${white}"
    fi
    hr
    bottom_line
    echo
}

install_spoolup() {
    print_banner
    print_requirements
    
    local yn
    install_msg "SpoolUp" yn
    
    case "$yn" in
        [Yy]*)
            echo
            detect_os
            check_requirements
            install_system_deps
            clone_repo
            setup_venv
            install_python_deps
            create_config
            create_service
            print_next_steps
            ;;
        [Nn]*)
            error_msg "Installation cancelled"
            exit 0
            ;;
        *)
            error_msg "Invalid choice"
            exit 1
            ;;
    esac
}

install_spoolup
