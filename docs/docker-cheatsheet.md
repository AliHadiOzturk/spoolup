# Docker Quick Reference

## Build

```bash
# Build image
docker build -t video-management-system .

# Build with no cache
docker build --no-cache -t video-management-system .
```

## Run

```bash
# Run with environment variables
docker run -d \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret \
  -e MOONRAKER_URL=http://printer-ip:4409 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --name vms \
  video-management-system
```

## Compose

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Restart
docker-compose restart

# Rebuild
docker-compose up -d --build
```

## Useful Commands

```bash
# Shell into container
docker-compose exec vms bash

# View running processes
docker-compose exec vms ps aux

# Check disk usage
docker-compose exec vms df -h

# Backup database
docker-compose exec vms cp /app/data/vms.db /app/data/vms.db.backup

# View container stats
docker stats vms
```

## Updating

```bash
# Pull latest
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

## Troubleshooting

```bash
# Container won't start
docker-compose logs vms

# Port already in use
lsof -i :8000

# Permission issues
sudo chown -R 1000:1000 ./data ./logs ./uploads

# Reset everything (WARNING: deletes data)
docker-compose down -v
rm -rf data/* logs/* uploads/*
docker-compose up -d
```