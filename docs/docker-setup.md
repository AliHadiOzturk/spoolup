# Docker Setup Guide

This guide explains how to run the Video Management System using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop
- Docker Compose 2.0+
- (Optional) YouTube/TikTok API credentials

## Quick Start

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd video-management-system
```

### 2. Configure Environment

Create a `.env` file from the example:

```bash
cp video_management/.env.example .env
```

Edit `.env` with your settings:

```env
# Required
SECRET_KEY=your-secure-random-key-here

# Your 3D Printer (Moonraker)
MOONRAKER_URL=http://your-printer-ip:4409
MOONRAKER_API_KEY=your-api-key-if-required

# YouTube (optional - needed for YouTube uploads)
YOUTUBE_CLIENT_SECRETS=/app/client_secrets.json

# TikTok (optional - needed for TikTok uploads)
TIKTOK_CLIENT_KEY=your-tiktok-client-key
TIKTOK_CLIENT_SECRET=your-tiktok-client-secret
```

### 3. Build and Run

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f vms

# Stop
docker-compose down
```

The web interface will be available at `http://localhost:8000`

## Configuration Options

### Using YouTube Uploads

1. Download your `client_secrets.json` from Google Cloud Console
2. Place it in the project root
3. Uncomment the volume mount in `docker-compose.yml`:

```yaml
volumes:
  - ./client_secrets.json:/app/client_secrets.json:ro
```

4. Set in `.env`:

```env
YOUTUBE_CLIENT_SECRETS=/app/client_secrets.json
```

### Using Tailscale for Printer Access

If your printer is on a Tailscale network:

1. Run the Docker container on the same Tailscale network
2. Or use Tailscale's subnet routing

```bash
# Option 1: Use host networking (Linux only)
docker-compose -f docker-compose.yml -f docker-compose.tailscale.yml up -d

# Option 2: Install Tailscale in container (advanced)
# See docker-compose.tailscale.yml
```

### Persistent Data

The following directories are persisted as volumes:

| Directory | Contents |
|-----------|----------|
| `./data` | SQLite database, YouTube tokens |
| `./logs` | Application logs |
| `./uploads` | Raw and processed videos |

## Docker Commands

```bash
# Build image
docker-compose build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Restart
docker-compose restart

# Stop and remove containers
docker-compose down

# Stop and remove containers + volumes (WARNING: deletes data!)
docker-compose down -v

# Execute command in container
docker-compose exec vms python -m video_management.database.init_db

# Shell access
docker-compose exec vms bash
```

## Production Deployment

### Using Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml vms

# Scale
docker service scale vms_vms=2
```

### Using Kubernetes

See `k8s/` directory for Kubernetes manifests (coming soon).

### Security Best Practices

1. **Never commit credentials**: `client_secrets.json`, `youtube_token.json`, `.env`
2. **Use secrets management**: Docker secrets, Kubernetes secrets, or vault
3. **Run as non-root**: Container uses `appuser` (UID 1000)
4. **Use HTTPS**: Put behind reverse proxy (nginx, traefik) with SSL
5. **Restrict network**: Only expose port 8000, use internal networks

### Reverse Proxy Example (nginx)

```nginx
server {
    listen 443 ssl;
    server_name vms.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs vms

# Check if port is in use
lsof -i :8000
```

### Can't connect to printer

```bash
# Test connectivity from container
docker-compose exec vms curl http://your-printer-ip:4409

# If using Tailscale, ensure container has network access
```

### Permission denied on volumes

```bash
# Fix permissions
sudo chown -R 1000:1000 ./data ./logs ./uploads
```

### FFmpeg not found

FFmpeg is included in the Docker image. If running locally, install it:

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg
```

## Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

## Environment Variables Reference

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `SECRET_KEY` | - | Yes | JWT secret key |
| `DATABASE_URL` | `sqlite:///data/vms.db` | Yes | Database path |
| `MOONRAKER_URL` | - | Yes | Printer Moonraker URL |
| `MOONRAKER_API_KEY` | - | No | Printer API key |
| `YOUTUBE_CLIENT_SECRETS` | - | No | Path to client_secrets.json |
| `YOUTUBE_TOKEN_FILE` | `data/youtube_token.json` | No | YouTube token storage |
| `TIKTOK_CLIENT_KEY` | - | No | TikTok app key |
| `TIKTOK_CLIENT_SECRET` | - | No | TikTok app secret |
| `FFMPEG_PATH` | `ffmpeg` | No | FFmpeg binary path |
| `MAX_VIDEO_DURATION` | `60` | No | Max video duration (seconds) |
| `OUTPUT_RESOLUTION` | `1080x1920` | No | Output resolution |
| `HOST` | `0.0.0.0` | No | Bind address |
| `PORT` | `8000` | No | Server port |
| `ANALYTICS_SYNC_HOUR` | `0` | No | Analytics sync hour |
| `ANALYTICS_SYNC_MINUTE` | `0` | No | Analytics sync minute |

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Video Management System README](../video_management/README.md)