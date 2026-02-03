#!/usr/bin/env python3
"""
Quick test script to verify the setup
"""

import os
import sys
import json
import subprocess


def test_python_version():
    """Test Python version"""
    print("✓ Testing Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 7:
        print(
            f"  ✓ Python {version.major}.{version.minor}.{version.micro} is compatible"
        )
        return True
    else:
        print(
            f"  ✗ Python {version.major}.{version.minor}.{version.micro} is too old (need 3.7+)"
        )
        return False


def test_imports():
    """Test required Python imports"""
    print("\n✓ Testing Python imports...")
    required = [
        ("requests", "requests"),
        ("websocket-client", "websocket"),
        ("google-api-python-client", "googleapiclient.discovery"),
        ("google-auth", "google.auth"),
        ("google-auth-oauthlib", "google_auth_oauthlib.flow"),
    ]

    all_ok = True
    for package, module in required:
        try:
            __import__(module)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ✗ {package} - NOT INSTALLED")
            all_ok = False

    return all_ok


def test_ffmpeg():
    """Test FFmpeg installation"""
    print("\n✓ Testing FFmpeg...")
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.split("\n")[0]
            print(f"  ✓ FFmpeg found: {version}")
            return True
        else:
            print("  ✗ FFmpeg found but returned error")
            return False
    except FileNotFoundError:
        print("  ✗ FFmpeg not found in PATH")
        return False
    except Exception as e:
        print(f"  ✗ Error checking FFmpeg: {e}")
        return False


def test_config():
    """Test configuration file"""
    print("\n✓ Testing configuration...")
    config_file = "config.json"

    if not os.path.exists(config_file):
        print(f"  ✗ Configuration file not found: {config_file}")
        print("  Run: python spoolup.py --create-config")
        return False

    try:
        with open(config_file, "r") as f:
            config = json.load(f)

        required_keys = ["moonraker_url", "webcam_url", "timelapse_dir"]
        missing = [k for k in required_keys if k not in config]

        if missing:
            print(f"  ✗ Missing required keys: {', '.join(missing)}")
            return False

        print(f"  ✓ Configuration file is valid")
        print(f"  ✓ Moonraker URL: {config['moonraker_url']}")
        print(f"  ✓ Webcam URL: {config['webcam_url']}")
        print(f"  ✓ Timelapse dir: {config['timelapse_dir']}")
        return True

    except json.JSONDecodeError as e:
        print(f"  ✗ Invalid JSON in config file: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Error reading config: {e}")
        return False


def test_credentials():
    """Test YouTube credentials file"""
    print("\n✓ Testing YouTube credentials...")

    # Check for client secrets
    if os.path.exists("client_secrets.json"):
        print("  ✓ client_secrets.json found")
        try:
            with open("client_secrets.json", "r") as f:
                secrets = json.load(f)
            if "installed" in secrets or "web" in secrets:
                print("  ✓ client_secrets.json appears valid")
                return True
            else:
                print("  ✗ client_secrets.json is missing required fields")
                return False
        except Exception as e:
            print(f"  ✗ Error reading client_secrets.json: {e}")
            return False
    else:
        print("  ✗ client_secrets.json not found")
        print("  Download from Google Cloud Console and save as client_secrets.json")
        return False


def test_moonraker():
    """Test Moonraker connection"""
    print("\n✓ Testing Moonraker connection...")

    config_data = None
    try:
        with open("config.json", "r") as f:
            config_data = json.load(f)

        import requests

        response = requests.get(
            f"{config_data['moonraker_url']}/printer/info", timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                print(f"  ✓ Moonraker is responding")
                print(f"  ✓ Klipper state: {data['result'].get('state', 'unknown')}")
                return True

        print(f"  ✗ Moonraker returned status {response.status_code}")
        return False

    except FileNotFoundError:
        print("  ✗ config.json not found")
        return False
    except Exception as e:
        if config_data is not None:
            print(
                f"  ✗ Cannot connect to Moonraker at {config_data.get('moonraker_url', 'unknown')}"
            )
        else:
            print(f"  ✗ Cannot connect to Moonraker")
        return False


def test_timelapse_dir():
    """Test timelapse directory"""
    print("\n✓ Testing timelapse directory...")

    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        timelapse_dir = config.get("timelapse_dir", "")

        if os.path.isdir(timelapse_dir):
            print(f"  ✓ Timelapse directory exists: {timelapse_dir}")
            files = [
                f
                for f in os.listdir(timelapse_dir)
                if f.endswith((".mp4", ".mkv", ".avi"))
            ]
            print(f"  ✓ Found {len(files)} video files in timelapse directory")
            return True
        else:
            print(f"  ✗ Timelapse directory not found: {timelapse_dir}")
            print("  Update timelapse_dir in config.json")
            return False

    except Exception as e:
        print(f"  ✗ Error checking timelapse directory: {e}")
        return False


def main():
    print("=" * 60)
    print("SpoolUp - Setup Test")
    print("=" * 60)
    print()

    results = []

    # Run tests
    results.append(("Python Version", test_python_version()))
    results.append(("Python Imports", test_imports()))
    results.append(("FFmpeg", test_ffmpeg()))
    results.append(("Configuration", test_config()))
    results.append(("YouTube Credentials", test_credentials()))

    # Only test these if config exists
    if os.path.exists("config.json"):
        results.append(("Moonraker Connection", test_moonraker()))
        results.append(("Timelapse Directory", test_timelapse_dir()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status} - {name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! You're ready to run the streamer.")
        print("   Run: python spoolup.py --auth-only")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        print("   See README.md for detailed setup instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
