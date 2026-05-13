# Video Management System (VMS)

A self-contained web-based video management system for 3D printer timelapse videos that uploads to YouTube Shorts and TikTok via official APIs, with analytics dashboard and midnight sync.

## Features

- **Video Discovery**: Automatically discovers timelapse videos from Moonraker-based 3D printers
- **Video Processing**: Converts 16:9 raw footage to 9:16 vertical format for short-form platforms using FFmpeg
- **Multi-Platform Upload**: Uploads to YouTube Shorts and TikTok using official APIs
- **Analytics Dashboard**: Tracks views, likes, comments, and shares with midnight sync
- **Multiple Printer Support**: Manage multiple printers from a single interface
- **Web Interface**: Modern dashboard for managing videos, uploads, and analytics

## Architecture

- **Self-Contained**: Everything runs inside the `video_management/` folder
- **Server-based**: Runs independently from printer hardware
- **Printer Communication**: Moonraker API over network (Tailscale compatible)
- **Database**: SQLite with SQLAlchemy ORM
- **Web Framework**: FastAPI with Jinja2 templates
- **Authentication**: JWT-based auth system

## Quick Start

### 1. Enter the video_management folder

```bash
cd video_management
```

### 2. Run Setup

```bash
./setup.sh
```

This will:
- Create a Python virtual environment at `video_management/venv/`
- Install all dependencies from `requirements.txt`
- Create data directories: `data/`, `logs/`, `uploads/raw/`, `uploads/processed/`
- Initialize the SQLite database at `data/vms.db`

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your settings
```

Example `.env`:
```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///data/vms.db
MOONRAKER_URL=http://192.168.1.115:4409
YOUTUBE_CLIENT_SECRETS=/path/to/client_secrets.json
TIKTOK_CLIENT_KEY=your-client-key
TIKTOK_CLIENT_SECRET=your-client-secret
HOST=0.0.0.0
PORT=8000
```

### 4. Run

```bash
# Activate virtual environment
source venv/bin/activate

# Start the server
python main.py
```

The web interface will be available at `http://localhost:8000`

### Development Mode

```bash
source venv/bin/activate
uvicorn ui.main:app --reload
```

## Project Structure

Everything is self-contained within `video_management/`:

```
video_management/
├── venv/                   # Python virtual environment
├── data/                   # SQLite database + tokens
│   └── vms.db             # Main database
├── logs/                   # Application logs
├── uploads/               # Video uploads
│   ├── raw/              # Original timelapse videos
│   └── processed/        # Processed 9:16 videos
├── main.py                # Application entry point
├── setup.sh               # Setup script
├── requirements.txt       # Dependencies
├── .env.example           # Configuration template
├── config/                # Configuration
│   └── __init__.py       # Settings management
├── database/              # Database layer
│   ├── __init__.py       # Engine, session, init
│   ├── models.py         # SQLAlchemy models
│   └── crud.py           # CRUD operations
├── auth/                  # Authentication
│   ├── __init__.py
│   ├── security.py       # Password hashing, JWT
│   └── dependencies.py   # FastAPI auth deps
├── api/                   # External API clients
│   ├── __init__.py
│   └── moonraker.py      # Moonraker printer API
├── video_processing/      # FFmpeg video processing
│   ├── __init__.py
│   └── processor.py      # Video conversion
├── uploaders/             # Platform uploaders
│   ├── __init__.py
│   ├── youtube.py        # YouTube Data API v3
│   └── tiktok.py         # TikTok Content Posting API
├── analytics/             # Analytics collection
│   ├── __init__.py
│   └── collector.py      # Metrics sync
├── scheduler.py           # Midnight sync scheduler
└── ui/                    # Web application
    ├── main.py           # FastAPI routes
    ├── static/           # CSS, JS, images
    │   ├── css/
    │   └── js/
    └── templates/        # HTML templates
        ├── base.html
        ├── dashboard.html
        ├── videos.html
        ├── uploads.html
        ├── analytics.html
        ├── printers.html
        ├── login.html
        └── index.html
```

## API Endpoints

### Authentication
- `POST /auth/register` - Register new user
- `POST /auth/login` - Login and get JWT token

### Videos
- `GET /api/videos` - List all videos
- `GET /api/videos/{id}` - Get video details
- `POST /api/videos/{id}/process` - Process video for shorts
- `GET /api/videos/{id}/processed` - List processed versions

### Uploads
- `POST /api/uploads/youtube/{processed_id}` - Upload to YouTube
- `POST /api/uploads/tiktok/{processed_id}` - Upload to TikTok
- `GET /api/uploads` - List all uploads
- `GET /api/uploads/{id}/status` - Check upload status

### Analytics
- `GET /api/analytics` - Get analytics dashboard data
- `GET /api/analytics/{upload_id}` - Get specific upload analytics

### Printers
- `GET /api/printers` - List printers
- `POST /api/printers` - Add printer
- `DELETE /api/printers/{id}` - Delete printer
- `POST /api/printers/{id}/sync` - Sync videos from printer

## Video Processing

The system automatically processes raw 16:9 timelapse footage into 9:16 vertical format:

- **Center Crop**: Crops center portion to 9:16 (default)
- **Smart Crop**: Follows print head movement (future)
- **Split Screen**: Shows multiple angles (future)

Options:
- Target duration (default 60s for Shorts)
- Speed multiplier
- Text overlays
- Custom resolution

## Analytics Sync

Analytics are automatically synced every midnight via APScheduler:
- YouTube: Views, likes, comments, favorites
- TikTok: Views, likes, comments, shares

## Requirements

- Python 3.8+
- FFmpeg (for video processing)
- YouTube Data API v3 credentials (optional)
- TikTok Content Posting API credentials (optional)

## Video Standards

### YouTube Shorts
- Duration: Max 60 seconds
- Aspect Ratio: 9:16 (1080x1920)
- Format: MP4

### TikTok
- Duration: Up to 10 minutes (recommend 3-60s)
- Aspect Ratio: 9:16 (540x960 minimum)
- Format: MP4
- File Size: Max 4GB (recommend <100MB)

## Development

### Running Tests

```bash
# From inside video_management/
cd video_management
source venv/bin/activate

# Syntax check
find . -name "*.py" -not -path "./venv/*" | xargs python -m py_compile

# Import test
python -c "from ui.main import app; print('OK')"
```

### Code Style

- 4 spaces indentation
- Double quotes for strings
- Type hints for all functions
- Module-level logger (no print statements)

## Troubleshooting

### "No module named 'video_management'"
Make sure you're running from inside the `video_management/` directory and have activated the virtual environment:
```bash
cd video_management
source venv/bin/activate
python main.py
```

### Database locked
SQLite doesn't support concurrent writes. Stop the server before running manual database operations.

### FFmpeg not found
Install FFmpeg on your system:
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: Download from https://ffmpeg.org/download.html

## License

MIT