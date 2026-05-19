#!/bin/bash

# Video Management System Setup Script
# Run this from INSIDE the video_management/ directory

set -e

echo "Setting up Video Management System..."
echo "Working directory: $(pwd)"

# Verify we're in the right place
if [ ! -f "requirements.txt" ]; then
    echo "ERROR: requirements.txt not found!"
    echo "Please cd into the video_management/ directory first:"
    echo "  cd video_management"
    echo "  ./setup.sh"
    exit 1
fi

# Create virtual environment inside this folder
if [ ! -d "venv" ]; then
    echo "Creating virtual environment at $(pwd)/venv ..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Create necessary directories inside this folder
echo "Creating directories..."
mkdir -p data
mkdir -p logs
mkdir -p uploads/raw
mkdir -p uploads/processed

# Initialize database
echo "Initializing database..."
python -c "from database import init_db; init_db()"

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Everything is self-contained in: $(pwd)"
echo ""
echo "To start the application:"
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "To start in development mode:"
echo "  source venv/bin/activate"
echo "  uvicorn ui.main:app --reload"
echo ""
echo "To configure, copy and edit .env:"
echo "  cp .env.example .env"
echo "  nano .env"
echo ""
echo "Database: $(pwd)/data/vms.db"
echo "Logs:     $(pwd)/logs/"
echo "Uploads:  $(pwd)/uploads/"
echo ""