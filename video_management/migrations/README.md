# Database Migrations

This directory contains Alembic database migrations for the Video Management System.

## Running Migrations

### Create a new migration
```bash
cd video_management
alembic revision --autogenerate -m "description"
```

### Apply migrations
```bash
cd video_management
alembic upgrade head
```

### Downgrade
```bash
cd video_management
alembic downgrade -1
```

## Initial Setup

Migrations are automatically run on application startup.

To manually initialize:
```bash
alembic init migrations
```

## Configuration

See `alembic.ini` for database connection settings.
