#!/usr/bin/env python3
"""
SpoolUp Authentication Tool

Handles YouTube OAuth authentication on PC/Mac.
Run this on your computer with a browser to generate the token file,
then copy the token to your printer.
"""

import os
import sys
import argparse
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Error: Google OAuth libraries not found.")
    print("Please install: pip install google-auth-oauthlib google-auth")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
]


def authenticate(client_secrets_path: str, output_path: str = "youtube_token.json"):
    """Run OAuth flow to authenticate with YouTube."""

    if not os.path.exists(client_secrets_path):
        print(f"Error: Client secrets file not found: {client_secrets_path}")
        print("\nPlease download your client secrets from Google Cloud Console:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project or select existing one")
        print("  3. Enable YouTube Data API v3")
        print("  4. Go to Credentials → Create Credentials → OAuth client ID")
        print("  5. Choose 'Desktop app' as application type")
        print("  6. Download the client secrets JSON file")
        return False

    print("=" * 60)
    print("  SpoolUp YouTube Authentication")
    print("=" * 60)
    print()
    print(f"Client secrets: {client_secrets_path}")
    print(f"Output token:   {output_path}")
    print()
    print("A browser window will open for you to authorize SpoolUp.")
    print("Please sign in with the Google account you want to use.")
    print()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)

        creds = flow.run_local_server(port=0)

        # Save the credentials
        with open(output_path, "w") as token_file:
            token_file.write(creds.to_json())

        print()
        print("=" * 60)
        print("  ✓ Authentication successful!")
        print("=" * 60)
        print()
        print(f"Token saved to: {os.path.abspath(output_path)}")
        print()
        print("Next steps:")
        print("  1. Copy this token file to your printer:")
        print(f"     scp {output_path} root@<printer_ip>:/path/to/spoolup/")
        print()
        print("  2. Restart SpoolUp service on your printer")
        print()

        return True

    except Exception as e:
        print()
        print("=" * 60)
        print("  ✗ Authentication failed")
        print("=" * 60)
        print()
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="SpoolUp Authentication Tool - Authenticate with YouTube on PC/Mac"
    )
    parser.add_argument(
        "--client-secrets",
        default="client_secrets.json",
        help="Path to Google OAuth client secrets file (default: client_secrets.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="youtube_token.json",
        help="Path to save the authentication token (default: youtube_token.json)",
    )

    args = parser.parse_args()

    success = authenticate(args.client_secrets, args.output)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
