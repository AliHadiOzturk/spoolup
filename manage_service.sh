#!/bin/sh
# Universal service manager wrapper - runs the Python manager
python3 "$(dirname "$0")/manage_service.py" "$@"
