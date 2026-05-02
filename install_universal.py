#!/usr/bin/env python3
"""
Universal SpoolUp Installer
Works on Linux, macOS, and Windows
"""

import os
import sys
import platform
import subprocess
import shutil
import json
from pathlib import Path
from typing import Optional, Dict, Any


class Colors:
    """ANSI color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def log(msg: str, level: str = "info") -> None:
    """Print colored log messages"""
    colors = {
        "info": Colors.BLUE,
        "success": Colors.GREEN,
        "warning": Colors.YELLOW,
        "error": Colors.RED,
        "header": Colors.CYAN + Colors.BOLD,
    }
    prefix = {
        "info": "ℹ ",
        "success": "✓ ",
        "warning": "⚠ ",
        "error": "✗ ",
        "header": "",
    }
    color = colors.get(level, Colors.BLUE)
    pre = prefix.get(level, "")
    print(f"{color}{pre}{msg}{Colors.ENDC}")


def run_cmd(cmd: list, check: bool = True, capture: bool = True) -> tuple:
    """Run shell command and return (returncode, stdout, stderr)"""
    try:
        if capture:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=check
            )
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, check=check)
            return result.returncode, "", ""
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.returncode, e.stdout or "", e.stderr or ""


class BaseInstaller:
    """Base class for platform-specific installers"""
    
    def __init__(self, script_dir: Path):
        self.script_dir = script_dir
        self.install_dir = self._get_install_dir()
        self.config_file = self.install_dir / "config.json"
        
    def _get_install_dir(self) -> Path:
        """Get installation directory based on platform"""
        raise NotImplementedError
        
    def check_requirements(self) -> bool:
        """Check if system meets requirements"""
        raise NotImplementedError
        
    def install_dependencies(self) -> None:
        """Install system dependencies"""
        raise NotImplementedError
        
    def copy_files(self) -> None:
        """Copy application files to install directory"""
        log("Copying application files...")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy Python files
        for py_file in self.script_dir.glob("*.py"):
            shutil.copy2(py_file, self.install_dir)
            
        # Copy directories
        for dir_name in ["spoolup", "spoolup_auth"]:
            src = self.script_dir / dir_name
            if src.exists():
                dst = self.install_dir / dir_name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
        
        # Copy requirements
        for req_file in ["requirements.txt", "requirements-auth.txt"]:
            src = self.script_dir / req_file
            if src.exists():
                shutil.copy2(src, self.install_dir)
                
        log("Files copied successfully", "success")
        
    def create_config(self) -> None:
        """Create default configuration file"""
        if self.config_file.exists():
            log("Configuration file already exists, skipping")
            return
            
        log("Creating default configuration...")
        
        config: Dict[str, Any] = {
            "moonraker_url": "http://localhost:7125",
            "webcam_url": "http://localhost:8080/?action=stream",
            "timelapse_dir": str(self._get_timelapse_dir()),
            "client_secrets_file": str(self.install_dir / "client_secrets.json"),
            "token_file": str(self.install_dir / "youtube_token.json"),
            "stream_resolution": "1280x720",
            "stream_fps": 30,
            "stream_bitrate": "4000k",
            "stream_privacy": "unlisted",
            "youtube_category_id": "28",
            "video_privacy": "private",
            "enable_live_stream": True,
            "enable_timelapse_upload": True,
        }
        
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
            
        log("Configuration created", "success")
        
    def _get_timelapse_dir(self) -> Path:
        """Get timelapse directory based on platform"""
        return self.install_dir / "timelapse"
        
    def install_python_deps(self) -> None:
        """Install Python dependencies"""
        log("Installing Python dependencies...")
        req_file = self.install_dir / "requirements.txt"
        if req_file.exists():
            run_cmd([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        log("Dependencies installed", "success")
        
    def create_service(self) -> None:
        """Create system service"""
        raise NotImplementedError
        
    def start_service(self) -> None:
        """Start the service"""
        raise NotImplementedError
        
    def print_next_steps(self) -> None:
        """Print next steps for user"""
        log("\n" + "="*60, "header")
        log("Installation Complete!", "success")
        log("="*60, "header")
        log(f"\nInstallation directory: {self.install_dir}")
        log("\nNext steps:")
        log("1. Get YouTube API credentials from https://console.cloud.google.com/")
        log("2. Save client_secrets.json to the installation directory")
        log("3. Authenticate: python -m spoolup_auth --client-secrets client_secrets.json")
        log("4. Start the service")
        
    def install(self) -> None:
        """Run full installation"""
        self.print_banner()
        
        if not self.check_requirements():
            log("Requirements check failed", "error")
            sys.exit(1)
            
        self.install_dependencies()
        self.copy_files()
        self.create_config()
        self.install_python_deps()
        self.create_service()
        self.print_next_steps()
        
    def print_banner(self) -> None:
        """Print installation banner"""
        log("\n" + "="*60, "header")
        log("SpoolUp Universal Installer", "header")
        log("="*60, "header")
        log("\nAutomatically stream your 3D prints to YouTube Live")
        log("and upload timelapse videos when prints complete.\n")


class LinuxInstaller(BaseInstaller):
    """Linux installer with systemd support"""
    
    def _get_install_dir(self) -> Path:
        if Path("/usr/data").exists():
            return Path("/usr/data/spoolup")
        elif Path("/opt").exists():
            return Path("/opt/spoolup")
        else:
            return Path.home() / ".local" / "spoolup"
            
    def _get_timelapse_dir(self) -> Path:
        if Path("/usr/data/printer_data/timelapse").exists():
            return Path("/usr/data/printer_data/timelapse")
        elif Path("/home/pi/printer_data/timelapse").exists():
            return Path("/home/pi/printer_data/timelapse")
        else:
            return self.install_dir / "timelapse"
            
    def check_requirements(self) -> bool:
        log("Checking requirements...")
        
        # Check Python
        py_version = sys.version_info
        if py_version < (3, 7):
            log(f"Python 3.7+ required, found {py_version.major}.{py_version.minor}", "error")
            return False
        log(f"Python {py_version.major}.{py_version.minor} OK", "success")
        
        # Check FFmpeg
        if shutil.which("ffmpeg"):
            log("FFmpeg found", "success")
        else:
            log("FFmpeg not found - will attempt to install", "warning")
            
        return True
        
    def install_dependencies(self) -> None:
        log("Installing system dependencies...")
        
        if shutil.which("apt-get"):
            run_cmd(["sudo", "apt-get", "update"], check=False)
            run_cmd(["sudo", "apt-get", "install", "-y", "ffmpeg", "python3-pip"], check=False)
        elif shutil.which("yum"):
            run_cmd(["sudo", "yum", "install", "-y", "ffmpeg", "python3-pip"], check=False)
        elif shutil.which("pacman"):
            run_cmd(["sudo", "pacman", "-S", "--noconfirm", "ffmpeg", "python-pip"], check=False)
        elif shutil.which("opkg"):
            run_cmd(["opkg", "update"], check=False)
            run_cmd(["opkg", "install", "ffmpeg"], check=False)
            
    def create_service(self) -> None:
        log("Creating systemd service...")
        
        service_content = f"""[Unit]
Description=SpoolUp - YouTube Streamer for 3D Prints
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={self.install_dir}
ExecStart={sys.executable} -m spoolup -c {self.config_file}
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
"""
        
        service_path = Path("/etc/systemd/system/spoolup.service")
        
        try:
            # Try to write with sudo
            cmd = ["sudo", "tee", str(service_path)]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True)
            proc.communicate(input=service_content)
            
            if proc.returncode == 0:
                run_cmd(["sudo", "systemctl", "daemon-reload"])
                run_cmd(["sudo", "systemctl", "enable", "spoolup"])
                log("Systemd service created and enabled", "success")
            else:
                # Fallback: create user service
                user_service_dir = Path.home() / ".config" / "systemd" / "user"
                user_service_dir.mkdir(parents=True, exist_ok=True)
                user_service_path = user_service_dir / "spoolup.service"
                
                with open(user_service_path, "w") as f:
                    f.write(service_content)
                    
                run_cmd(["systemctl", "--user", "daemon-reload"])
                run_cmd(["systemctl", "--user", "enable", "spoolup"])
                log("User systemd service created", "success")
                
        except Exception as e:
            log(f"Failed to create systemd service: {e}", "warning")
            log("You can run the application manually", "warning")
            
    def print_next_steps(self) -> None:
        super().print_next_steps()
        log("\nService commands:")
        log("  Start:   sudo systemctl start spoolup")
        log("  Stop:    sudo systemctl stop spoolup")
        log("  Status:  sudo systemctl status spoolup")
        log("  Logs:    sudo journalctl -u spoolup -f")
        log("\nOr for user service:")
        log("  systemctl --user start spoolup")


class MacOSInstaller(BaseInstaller):
    """macOS installer with launchd support"""
    
    def _get_install_dir(self) -> Path:
        return Path.home() / "Applications" / "spoolup"
        
    def _get_timelapse_dir(self) -> Path:
        return self.install_dir / "timelapse"
        
    def check_requirements(self) -> bool:
        log("Checking requirements...")
        
        py_version = sys.version_info
        if py_version < (3, 7):
            log(f"Python 3.7+ required, found {py_version.major}.{py_version.minor}", "error")
            return False
        log(f"Python {py_version.major}.{py_version.minor} OK", "success")
        
        if shutil.which("ffmpeg"):
            log("FFmpeg found", "success")
        else:
            log("FFmpeg not found. Install with: brew install ffmpeg", "warning")
            
        return True
        
    def install_dependencies(self) -> None:
        log("Installing dependencies...")
        if shutil.which("brew"):
            run_cmd(["brew", "install", "ffmpeg"], check=False)
            
    def create_service(self) -> None:
        log("Creating launchd service...")
        
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.spoolup.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>spoolup</string>
        <string>-c</string>
        <string>{self.config_file}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{self.install_dir}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{self.install_dir}/spoolup.log</string>
    <key>StandardErrorPath</key>
    <string>{self.install_dir}/spoolup.log</string>
</dict>
</plist>
"""
        
        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        launch_agents_dir.mkdir(parents=True, exist_ok=True)
        
        plist_path = launch_agents_dir / "com.spoolup.app.plist"
        with open(plist_path, "w") as f:
            f.write(plist_content)
            
        # Load the service
        run_cmd(["launchctl", "load", str(plist_path)], check=False)
        log("Launchd service created", "success")
        
    def print_next_steps(self) -> None:
        super().print_next_steps()
        log("\nService commands:")
        log("  Start:   launchctl start com.spoolup.app")
        log("  Stop:    launchctl stop com.spoolup.app")
        log("  Logs:    tail -f ~/Applications/spoolup/spoolup.log")


class WindowsInstaller(BaseInstaller):
    """Windows installer with scheduled task support"""
    
    def _get_install_dir(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA", "")) / "spoolup"
        
    def _get_timelapse_dir(self) -> Path:
        return self.install_dir / "timelapse"
        
    def check_requirements(self) -> bool:
        log("Checking requirements...")
        
        py_version = sys.version_info
        if py_version < (3, 7):
            log(f"Python 3.7+ required, found {py_version.major}.{py_version.minor}", "error")
            return False
        log(f"Python {py_version.major}.{py_version.minor} OK", "success")
        
        if shutil.which("ffmpeg"):
            log("FFmpeg found", "success")
        else:
            log("FFmpeg not found. Download from https://ffmpeg.org/download.html", "warning")
            
        return True
        
    def install_dependencies(self) -> None:
        log("Installing dependencies...")
        # Windows typically doesn't need system deps
        pass
        
    def create_service(self) -> None:
        log("Creating Windows scheduled task...")
        
        # Create a batch file to run the service
        batch_file = self.install_dir / "run_spoolup.bat"
        batch_content = f"""@echo off
cd /d "{self.install_dir}"
"{sys.executable}" -m spoolup -c "{self.config_file}"
"""
        with open(batch_file, "w") as f:
            f.write(batch_content)
            
        # Create scheduled task using schtasks
        task_name = "SpoolUpService"
        
        # Delete existing task if any
        run_cmd(["schtasks", "/delete", "/tn", task_name, "/f"], check=False)
        
        # Create new task
        create_cmd = [
            "schtasks", "/create",
            "/tn", task_name,
            "/tr", f'"{batch_file}"',
            "/sc", "onstart",
            "/ru", "SYSTEM",
            "/rl", "HIGHEST",
            "/f"
        ]
        
        try:
            run_cmd(create_cmd)
            log("Windows scheduled task created", "success")
        except Exception as e:
            log(f"Failed to create scheduled task: {e}", "warning")
            log("You can run the application manually", "warning")
            
    def print_next_steps(self) -> None:
        super().print_next_steps()
        log("\nService commands:")
        log("  Start:   schtasks /run /tn SpoolUpService")
        log("  Stop:    schtasks /end /tn SpoolUpService")
        log("  Status:  schtasks /query /tn SpoolUpService")
        log(f"\nOr run manually: {self.install_dir / 'run_spoolup.bat'}")


def get_installer() -> BaseInstaller:
    """Factory function to get appropriate installer for current platform"""
    system = platform.system().lower()
    script_dir = Path(__file__).parent.resolve()
    
    if system == "linux":
        return LinuxInstaller(script_dir)
    elif system == "darwin":
        return MacOSInstaller(script_dir)
    elif system == "windows":
        return WindowsInstaller(script_dir)
    else:
        log(f"Unsupported platform: {system}", "error")
        sys.exit(1)


def main() -> None:
    """Main entry point"""
    try:
        installer = get_installer()
        installer.install()
    except KeyboardInterrupt:
        log("\nInstallation cancelled by user", "warning")
        sys.exit(1)
    except Exception as e:
        log(f"Installation failed: {e}", "error")
        sys.exit(1)


if __name__ == "__main__":
    main()
