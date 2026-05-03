#!/usr/bin/env python3
"""
Universal SpoolUp Service Manager
Works on Linux (systemd/init.d), macOS (launchd), and Windows (schtasks)
"""

import os
import sys
import platform
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, List, Tuple
from enum import Enum


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
    if platform.system().lower() == "windows" and not os.environ.get("WT_SESSION"):
        print(msg)
        return
        
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


def run_cmd(cmd: list, check: bool = True, capture: bool = True) -> Tuple[int, str, str]:
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


class ServiceStatus(Enum):
    """Service status enumeration"""
    RUNNING = "running"
    STOPPED = "stopped"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"


class BaseServiceManager:
    """Base class for platform-specific service managers"""
    
    def __init__(self):
        self.service_name = "spoolup"
        self.install_dir = self._get_install_dir()
        self.log_file = self._get_log_file()
        
    def _get_install_dir(self) -> Path:
        """Get installation directory based on platform"""
        raise NotImplementedError
        
    def _get_log_file(self) -> Path:
        """Get log file path"""
        return self.install_dir / "spoolup.log"
        
    def get_status(self) -> ServiceStatus:
        """Get current service status"""
        raise NotImplementedError
        
    def start(self) -> bool:
        """Start the service"""
        raise NotImplementedError
        
    def stop(self) -> bool:
        """Stop the service"""
        raise NotImplementedError
        
    def restart(self) -> bool:
        """Restart the service"""
        raise NotImplementedError
        
    def enable(self) -> bool:
        """Enable service to start on boot"""
        raise NotImplementedError
        
    def disable(self) -> bool:
        """Disable service from starting on boot"""
        raise NotImplementedError
        
    def view_logs(self, lines: int = 50, follow: bool = False) -> None:
        """View service logs"""
        raise NotImplementedError
        
    def install(self) -> bool:
        """Install the service"""
        raise NotImplementedError
        
    def uninstall(self) -> bool:
        """Uninstall the service"""
        raise NotImplementedError
        
    def print_status(self) -> None:
        """Print formatted status"""
        status = self.get_status()
        
        log("\n" + "="*60, "header")
        log("SpoolUp Service Status", "header")
        log("="*60, "header")
        
        if status == ServiceStatus.RUNNING:
            log(f"Status: {status.value.upper()}", "success")
        elif status == ServiceStatus.STOPPED:
            log(f"Status: {status.value.upper()}", "warning")
        elif status == ServiceStatus.NOT_INSTALLED:
            log(f"Status: {status.value.upper()}", "error")
            log("Service not installed. Run install_universal.py first", "error")
        else:
            log(f"Status: {status.value.upper()}", "error")
            
        log(f"\nInstall Directory: {self.install_dir}")
        log(f"Log File: {self.log_file}")
        
        if status != ServiceStatus.NOT_INSTALLED:
            log("\nUseful commands:")
            log("  python3 manage_service.py start    - Start service")
            log("  python3 manage_service.py stop     - Stop service")
            log("  python3 manage_service.py restart  - Restart service")
            log("  python3 manage_service.py logs     - View logs")
            log("  python3 manage_service.py enable   - Enable auto-start")
            log("  python3 manage_service.py disable  - Disable auto-start")
        
        log("="*60 + "\n")


class LinuxServiceManager(BaseServiceManager):
    """Linux service manager with systemd/init.d support"""
    
    def __init__(self):
        super().__init__()
        self.systemd_available = self._check_systemd()
        self.service_name = "spoolup"
        
    def _get_install_dir(self) -> Path:
        if Path("/usr/data/spoolup").exists():
            return Path("/usr/data/spoolup")
        elif Path("/opt/spoolup").exists():
            return Path("/opt/spoolup")
        else:
            return Path.home() / ".local" / "spoolup"
            
    def _get_log_file(self) -> Path:
        if Path("/var/log/spoolup.log").exists():
            return Path("/var/log/spoolup.log")
        return self.install_dir / "spoolup.log"
        
    def _check_systemd(self) -> bool:
        """Check if systemd is available"""
        return (
            shutil.which("systemctl") is not None and
            Path("/etc/systemd/system").exists()
        )
        
    def _get_service_file(self) -> Optional[Path]:
        """Find service file location"""
        locations = [
            Path("/etc/systemd/system/spoolup.service"),
            Path("/etc/init.d/S99spoolup"),
            Path.home() / ".config" / "systemd" / "user" / "spoolup.service",
        ]
        for loc in locations:
            if loc.exists():
                return loc
        return None
        
    def get_status(self) -> ServiceStatus:
        """Get service status"""
        service_file = self._get_service_file()
        if not service_file:
            return ServiceStatus.NOT_INSTALLED
            
        if self.systemd_available:
            try:
                code, stdout, _ = run_cmd(
                    ["systemctl", "is-active", self.service_name],
                    check=False
                )
                if code == 0:
                    return ServiceStatus.RUNNING
                else:
                    return ServiceStatus.STOPPED
            except Exception:
                return ServiceStatus.ERROR
        else:
            # init.d
            try:
                pid_file = Path("/var/run/spoolup.pid")
                if pid_file.exists():
                    pid = pid_file.read_text().strip()
                    try:
                        os.kill(int(pid), 0)
                        return ServiceStatus.RUNNING
                    except (OSError, ValueError):
                        return ServiceStatus.STOPPED
                return ServiceStatus.STOPPED
            except Exception:
                return ServiceStatus.ERROR
                
    def start(self) -> bool:
        """Start service"""
        if self.systemd_available:
            try:
                run_cmd(["sudo", "systemctl", "start", self.service_name])
                log("Service started successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to start service: {e}", "error")
                return False
        else:
            # init.d
            try:
                run_cmd(["/etc/init.d/S99spoolup", "start"])
                log("Service started successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to start service: {e}", "error")
                return False
                
    def stop(self) -> bool:
        """Stop service"""
        if self.systemd_available:
            try:
                run_cmd(["sudo", "systemctl", "stop", self.service_name])
                log("Service stopped successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to stop service: {e}", "error")
                return False
        else:
            # init.d
            try:
                run_cmd(["/etc/init.d/S99spoolup", "stop"])
                log("Service stopped successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to stop service: {e}", "error")
                return False
                
    def restart(self) -> bool:
        """Restart service"""
        if self.systemd_available:
            try:
                run_cmd(["sudo", "systemctl", "restart", self.service_name])
                log("Service restarted successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to restart service: {e}", "error")
                return False
        else:
            # init.d
            try:
                run_cmd(["/etc/init.d/S99spoolup", "restart"])
                log("Service restarted successfully", "success")
                return True
            except Exception as e:
                log(f"Failed to restart service: {e}", "error")
                return False
                
    def enable(self) -> bool:
        """Enable service on boot"""
        if self.systemd_available:
            try:
                run_cmd(["sudo", "systemctl", "enable", self.service_name])
                log("Service enabled to start on boot", "success")
                return True
            except Exception as e:
                log(f"Failed to enable service: {e}", "error")
                return False
        else:
            log("Init.d services auto-start by default", "info")
            return True
            
    def disable(self) -> bool:
        """Disable service on boot"""
        if self.systemd_available:
            try:
                run_cmd(["sudo", "systemctl", "disable", self.service_name])
                log("Service disabled from starting on boot", "success")
                return True
            except Exception as e:
                log(f"Failed to disable service: {e}", "error")
                return False
        else:
            # Remove from init.d
            try:
                init_file = Path("/etc/init.d/S99spoolup")
                if init_file.exists():
                    init_file.unlink()
                log("Service disabled from starting on boot", "success")
                return True
            except Exception as e:
                log(f"Failed to disable service: {e}", "error")
                return False
                
    def view_logs(self, lines: int = 50, follow: bool = False) -> None:
        """View service logs"""
        if self.systemd_available:
            cmd = ["sudo", "journalctl", "-u", self.service_name, "-n", str(lines)]
            if follow:
                cmd.append("-f")
            try:
                run_cmd(cmd, capture=False)
            except KeyboardInterrupt:
                print()
        else:
            # Read log file directly
            log_file = self._get_log_file()
            if not log_file.exists():
                log(f"Log file not found: {log_file}", "error")
                return
                
            if follow:
                try:
                    # Use tail -f
                    run_cmd(["tail", "-f", str(log_file)], capture=False)
                except KeyboardInterrupt:
                    print()
            else:
                try:
                    with open(log_file, "r") as f:
                        all_lines = f.readlines()
                        for line in all_lines[-lines:]:
                            print(line.rstrip())
                except Exception as e:
                    log(f"Failed to read logs: {e}", "error")
                    
    def install(self) -> bool:
        """Install the service"""
        log("Installing SpoolUp service...")
        
        if self.get_status() != ServiceStatus.NOT_INSTALLED:
            log("Service is already installed. Use 'update' to reinstall.", "warning")
            return False
            
        try:
            # Create service file
            if self.systemd_available:
                service_content = f"""[Unit]
Description=SpoolUp - YouTube Streamer for 3D Prints
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={self.install_dir}
ExecStart={sys.executable} -m spoolup -c {self.install_dir / 'config.json'}
Restart=always
RestartSec=10
StandardOutput=append:/var/log/spoolup.log
StandardError=append:/var/log/spoolup.log

[Install]
WantedBy=multi-user.target
"""
                service_path = Path("/etc/systemd/system/spoolup.service")
                
                # Try with sudo
                proc = subprocess.Popen(
                    ["sudo", "tee", str(service_path)],
                    stdin=subprocess.PIPE,
                    text=True
                )
                proc.communicate(input=service_content)
                
                if proc.returncode == 0:
                    run_cmd(["sudo", "systemctl", "daemon-reload"])
                    run_cmd(["sudo", "systemctl", "enable", self.service_name])
                    log("Systemd service installed successfully", "success")
                    return True
                else:
                    # Fallback to user service
                    user_service_dir = Path.home() / ".config" / "systemd" / "user"
                    user_service_dir.mkdir(parents=True, exist_ok=True)
                    user_service_path = user_service_dir / "spoolup.service"
                    
                    with open(user_service_path, "w") as f:
                        f.write(service_content)
                        
                    run_cmd(["systemctl", "--user", "daemon-reload"])
                    run_cmd(["systemctl", "--user", "enable", self.service_name])
                    log("User systemd service installed successfully", "success")
                    return True
            else:
                # init.d
                init_content = f"""#!/bin/sh
# SpoolUp service

cd {self.install_dir}

case "$1" in
    start)
        echo "Starting SpoolUp..."
        {sys.executable} -m spoolup -c {self.install_dir / 'config.json'} > /var/log/spoolup.log 2>&1 &
        echo $! > /var/run/spoolup.pid
        ;;
    stop)
        echo "Stopping SpoolUp..."
        if [ -f /var/run/spoolup.pid ]; then
            kill $(cat /var/run/spoolup.pid) 2>/dev/null
            rm -f /var/run/spoolup.pid
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f /var/run/spoolup.pid ] && kill -0 $(cat /var/run/spoolup.pid) 2>/dev/null; then
            echo "SpoolUp is running"
        else
            echo "SpoolUp is not running"
        fi
        ;;
    *)
        echo "Usage: $0 {{start|stop|restart|status}}"
        exit 1
        ;;
esac
"""
                init_path = Path("/etc/init.d/S99spoolup")
                proc = subprocess.Popen(
                    ["sudo", "tee", str(init_path)],
                    stdin=subprocess.PIPE,
                    text=True
                )
                proc.communicate(input=init_content)
                
                if proc.returncode == 0:
                    run_cmd(["sudo", "chmod", "+x", str(init_path)])
                    log("Init.d service installed successfully", "success")
                    return True
                else:
                    log("Failed to install init.d service (permission denied)", "error")
                    return False
                    
        except Exception as e:
            log(f"Installation failed: {e}", "error")
            return False
            
    def uninstall(self) -> bool:
        """Uninstall the service"""
        log("Uninstalling SpoolUp service...")
        
        try:
            # Stop service first
            self.stop()
            
            # Remove service file
            service_file = self._get_service_file()
            if service_file:
                if self.systemd_available:
                    try:
                        run_cmd(["sudo", "systemctl", "disable", self.service_name])
                        run_cmd(["sudo", "rm", str(service_file)])
                        run_cmd(["sudo", "systemctl", "daemon-reload"])
                        log("Systemd service removed", "success")
                    except Exception:
                        # Try user service
                        user_service = Path.home() / ".config" / "systemd" / "user" / "spoolup.service"
                        if user_service.exists():
                            run_cmd(["systemctl", "--user", "disable", self.service_name])
                            user_service.unlink()
                            run_cmd(["systemctl", "--user", "daemon-reload"])
                            log("User systemd service removed", "success")
                else:
                    # init.d
                    try:
                        run_cmd(["sudo", "rm", str(service_file)])
                        log("Init.d service removed", "success")
                    except Exception as e:
                        log(f"Failed to remove init.d service: {e}", "error")
                        
            # Optionally remove installation directory
            if self.install_dir.exists() and input(f"\nRemove installation directory {self.install_dir}? [y/N]: ").lower() == 'y':
                shutil.rmtree(self.install_dir)
                log(f"Removed {self.install_dir}", "success")
                
            log("Uninstall complete", "success")
            return True
            
        except Exception as e:
            log(f"Uninstall failed: {e}", "error")
            return False


class MacOSServiceManager(BaseServiceManager):
    """macOS service manager with launchd support"""
    
    def __init__(self):
        super().__init__()
        self.plist_name = "com.spoolup.app"
        self.plist_path = Path.home() / "Library" / "LaunchAgents" / f"{self.plist_name}.plist"
        
    def _get_install_dir(self) -> Path:
        return Path.home() / "Applications" / "spoolup"
        
    def _get_log_file(self) -> Path:
        return self.install_dir / "spoolup.log"
        
    def get_status(self) -> ServiceStatus:
        """Get service status"""
        if not self.plist_path.exists():
            return ServiceStatus.NOT_INSTALLED
            
        try:
            code, stdout, _ = run_cmd(
                ["launchctl", "list", self.plist_name],
                check=False
            )
            if code == 0 and "PID" in stdout:
                return ServiceStatus.RUNNING
            else:
                return ServiceStatus.STOPPED
        except Exception:
            return ServiceStatus.ERROR
            
    def start(self) -> bool:
        """Start service"""
        try:
            run_cmd(["launchctl", "start", self.plist_name])
            log("Service started successfully", "success")
            return True
        except Exception as e:
            log(f"Failed to start service: {e}", "error")
            return False
            
    def stop(self) -> bool:
        """Stop service"""
        try:
            run_cmd(["launchctl", "stop", self.plist_name])
            log("Service stopped successfully", "success")
            return True
        except Exception as e:
            log(f"Failed to stop service: {e}", "error")
            return False
            
    def restart(self) -> bool:
        """Restart service"""
        try:
            self.stop()
            time.sleep(2)
            self.start()
            return True
        except Exception as e:
            log(f"Failed to restart service: {e}", "error")
            return False
            
    def enable(self) -> bool:
        """Enable service on boot"""
        try:
            run_cmd(["launchctl", "load", str(self.plist_path)])
            log("Service enabled to start on boot", "success")
            return True
        except Exception as e:
            log(f"Failed to enable service: {e}", "error")
            return False
            
    def disable(self) -> bool:
        """Disable service on boot"""
        try:
            run_cmd(["launchctl", "unload", str(self.plist_path)])
            log("Service disabled from starting on boot", "success")
            return True
        except Exception as e:
            log(f"Failed to disable service: {e}", "error")
            return False
            
    def view_logs(self, lines: int = 50, follow: bool = False) -> None:
        """View service logs"""
        log_file = self._get_log_file()
        if not log_file.exists():
            log(f"Log file not found: {log_file}", "error")
            return
            
        if follow:
            try:
                run_cmd(["tail", "-f", str(log_file)], capture=False)
            except KeyboardInterrupt:
                print()
        else:
            try:
                with open(log_file, "r") as f:
                    all_lines = f.readlines()
                    for line in all_lines[-lines:]:
                        print(line.rstrip())
            except Exception as e:
                log(f"Failed to read logs: {e}", "error")
                
    def install(self) -> bool:
        """Install the service"""
        log("Installing SpoolUp service...")
        
        if self.get_status() != ServiceStatus.NOT_INSTALLED:
            log("Service is already installed. Use 'update' to reinstall.", "warning")
            return False
            
        try:
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.plist_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>spoolup</string>
        <string>-c</string>
        <string>{self.install_dir / 'config.json'}</string>
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
            
            with open(self.plist_path, "w") as f:
                f.write(plist_content)
                
            # Load the service
            run_cmd(["launchctl", "load", str(self.plist_path)], check=False)
            log("Launchd service installed successfully", "success")
            return True
            
        except Exception as e:
            log(f"Installation failed: {e}", "error")
            return False
            
    def uninstall(self) -> bool:
        """Uninstall the service"""
        log("Uninstalling SpoolUp service...")
        
        try:
            # Stop service first
            self.stop()
            
            # Unload plist
            if self.plist_path.exists():
                run_cmd(["launchctl", "unload", str(self.plist_path)], check=False)
                self.plist_path.unlink()
                log("Launchd service removed", "success")
                
            # Optionally remove installation directory
            if self.install_dir.exists() and input(f"\nRemove installation directory {self.install_dir}? [y/N]: ").lower() == 'y':
                shutil.rmtree(self.install_dir)
                log(f"Removed {self.install_dir}", "success")
                
            log("Uninstall complete", "success")
            return True
            
        except Exception as e:
            log(f"Uninstall failed: {e}", "error")
            return False


class WindowsServiceManager(BaseServiceManager):
    """Windows service manager with schtasks support"""
    
    def __init__(self):
        super().__init__()
        self.task_name = "SpoolUpService"
        
    def _get_install_dir(self) -> Path:
        return Path(os.environ.get("LOCALAPPDATA", "")) / "spoolup"
        
    def _get_log_file(self) -> Path:
        return self.install_dir / "spoolup.log"
        
    def _is_admin(self) -> bool:
        """Check if running with administrator privileges"""
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
        
    def _task_exists(self) -> bool:
        """Check if scheduled task exists"""
        try:
            code, _, _ = run_cmd(
                ["schtasks", "/query", "/tn", self.task_name],
                check=False
            )
            return code == 0
        except Exception:
            return False
            
    def get_status(self) -> ServiceStatus:
        """Get service status"""
        if not self._task_exists():
            return ServiceStatus.NOT_INSTALLED
            
        try:
            code, stdout, _ = run_cmd(
                ["schtasks", "/query", "/tn", self.task_name, "/fo", "LIST"],
                check=False
            )
            if code == 0 and "Running" in stdout:
                return ServiceStatus.RUNNING
            else:
                return ServiceStatus.STOPPED
        except Exception:
            return ServiceStatus.ERROR
            
    def start(self) -> bool:
        """Start service"""
        if not self._task_exists():
            log("Service is not installed. Run 'install' first.", "error")
            return False
            
        try:
            run_cmd(["schtasks", "/run", "/tn", self.task_name])
            log("Service started successfully", "success")
            return True
        except Exception as e:
            log(f"Failed to start service: {e}", "error")
            return False
            
    def stop(self) -> bool:
        """Stop service"""
        if not self._task_exists():
            log("Service is not installed.", "error")
            return False
            
        try:
            run_cmd(["schtasks", "/end", "/tn", self.task_name])
            log("Service stopped successfully", "success")
            return True
        except Exception as e:
            log(f"Failed to stop service: {e}", "error")
            return False
            
    def restart(self) -> bool:
        """Restart service"""
        try:
            self.stop()
            time.sleep(2)
            self.start()
            return True
        except Exception as e:
            log(f"Failed to restart service: {e}", "error")
            return False
            
    def enable(self) -> bool:
        """Enable service on boot"""
        if not self._task_exists():
            log("Service is not installed.", "error")
            return False
            
        try:
            run_cmd(["schtasks", "/change", "/tn", self.task_name, "/ENABLE"])
            log("Service enabled to start on boot", "success")
            return True
        except Exception as e:
            log(f"Failed to enable service: {e}", "error")
            return False
            
    def disable(self) -> bool:
        """Disable service on boot"""
        if not self._task_exists():
            log("Service is not installed.", "error")
            return False
            
        try:
            run_cmd(["schtasks", "/change", "/tn", self.task_name, "/DISABLE"])
            log("Service disabled from starting on boot", "success")
            return True
        except Exception as e:
            log(f"Failed to disable service: {e}", "error")
            return False
            
    def view_logs(self, lines: int = 50, follow: bool = False) -> None:
        """View service logs"""
        log_file = self._get_log_file()
        if not log_file.exists():
            log(f"Log file not found: {log_file}", "error")
            return
            
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(line.rstrip())
        except Exception as e:
            log(f"Failed to read logs: {e}", "error")
            
    def install(self) -> bool:
        """Install the service"""
        log("Installing SpoolUp service...")
        
        if self._task_exists():
            log("Service is already installed. Use 'update' to reinstall.", "warning")
            return False
            
        # Check for admin privileges
        is_admin = self._is_admin()
        if not is_admin:
            log("Administrator privileges required for system-wide installation.", "warning")
            log("Please run as Administrator or the service will run as current user only.", "warning")
            use_current_user = input("Install for current user only? [Y/n]: ").lower() != 'n'
            if not use_current_user:
                log("Installation cancelled. Please run as Administrator.", "error")
                return False
        
        try:
            # Create batch file to run the service
            batch_file = self.install_dir / "run_spoolup.bat"
            batch_content = f"""@echo off
cd /d "{self.install_dir}"
"{sys.executable}" -m spoolup -c "{self.install_dir / 'config.json'}"
"""
            self.install_dir.mkdir(parents=True, exist_ok=True)
            with open(batch_file, "w") as f:
                f.write(batch_content)
                
            # Create scheduled task
            if is_admin:
                # System-wide task with highest privileges
                create_cmd = [
                    "schtasks", "/create",
                    "/tn", self.task_name,
                    "/tr", f'"{batch_file}"',
                    "/sc", "onstart",
                    "/ru", "SYSTEM",
                    "/rl", "HIGHEST",
                    "/f"
                ]
            else:
                # User-level task (runs when user logs in)
                create_cmd = [
                    "schtasks", "/create",
                    "/tn", self.task_name,
                    "/tr", f'"{batch_file}"',
                    "/sc", "onlogon",
                    "/f"
                ]
            
            code, stdout, stderr = run_cmd(create_cmd, check=False)
            if code != 0:
                error_msg = stderr or stdout or "Unknown error"
                log(f"schtasks failed: {error_msg}", "error")
                return False
                
            log("Windows scheduled task installed successfully", "success")
            if not is_admin:
                log("Note: Service will run when you log in (user-level)", "info")
            return True
            
        except Exception as e:
            log(f"Installation failed: {e}", "error")
            return False
            
    def uninstall(self) -> bool:
        """Uninstall the service"""
        log("Uninstalling SpoolUp service...")
        
        try:
            # Stop service first
            if self._task_exists():
                self.stop()
            
            # Remove scheduled task
            if self._task_exists():
                code, stdout, stderr = run_cmd(
                    ["schtasks", "/delete", "/tn", self.task_name, "/f"],
                    check=False
                )
                if code == 0:
                    log("Windows scheduled task removed", "success")
                else:
                    error_msg = stderr or stdout or "Unknown error"
                    log(f"Failed to remove task: {error_msg}", "error")
                    
            # Optionally remove installation directory
            if self.install_dir.exists() and input(f"\nRemove installation directory {self.install_dir}? [y/N]: ").lower() == 'y':
                shutil.rmtree(self.install_dir)
                log(f"Removed {self.install_dir}", "success")
                
            log("Uninstall complete", "success")
            return True
            
        except Exception as e:
            log(f"Uninstall failed: {e}", "error")
            return False


def get_service_manager() -> BaseServiceManager:
    """Factory function to get appropriate service manager"""
    system = platform.system().lower()
    
    if system == "linux":
        return LinuxServiceManager()
    elif system == "darwin":
        return MacOSServiceManager()
    elif system == "windows":
        return WindowsServiceManager()
    else:
        log(f"Unsupported platform: {system}", "error")
        sys.exit(1)


def print_help() -> None:
    """Print help message"""
    log("\n" + "="*60, "header")
    log("SpoolUp Service Manager", "header")
    log("="*60, "header")
    log("\nUsage: python3 manage_service.py <command>")
    log("\nCommands:")
    log("  install     Install SpoolUp as a system service")
    log("  uninstall   Uninstall SpoolUp service")
    log("  start       Start the SpoolUp service")
    log("  stop        Stop the SpoolUp service")
    log("  restart     Restart the SpoolUp service")
    log("  status      Show service status and information")
    log("  logs        View service logs (last 50 lines)")
    log("  logs -f     Follow logs in real-time (Ctrl+C to exit)")
    log("  enable      Enable service to start on boot")
    log("  disable     Disable service from starting on boot")
    log("  help        Show this help message")
    log("\nExamples:")
    log("  python3 manage_service.py install")
    log("  python3 manage_service.py start")
    log("  python3 manage_service.py logs -f")
    log("  python3 manage_service.py status")
    log("="*60 + "\n")


def main() -> None:
    """Main entry point"""
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
        
    command = sys.argv[1].lower()
    manager = get_service_manager()
    
    if command == "help" or command == "-h" or command == "--help":
        print_help()
        
    elif command == "status":
        manager.print_status()
        
    elif command == "start":
        manager.start()
        
    elif command == "stop":
        manager.stop()
        
    elif command == "restart":
        manager.restart()
        
    elif command == "logs":
        follow = "-f" in sys.argv or "--follow" in sys.argv
        lines = 50
        for i, arg in enumerate(sys.argv):
            if arg == "-n" and i + 1 < len(sys.argv):
                try:
                    lines = int(sys.argv[i + 1])
                except ValueError:
                    pass
        manager.view_logs(lines=lines, follow=follow)
        
    elif command == "enable":
        manager.enable()
        
    elif command == "disable":
        manager.disable()
        
    elif command == "install":
        manager.install()
        
    elif command == "uninstall":
        manager.uninstall()
        
    else:
        log(f"Unknown command: {command}", "error")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nOperation cancelled by user", "warning")
        sys.exit(1)
    except Exception as e:
        log(f"Error: {e}", "error")
        sys.exit(1)
