# Platform API Documentation Index

## Overview
This directory contains comprehensive documentation for integrating with the platform APIs used by the Video Management System.

## Documents

### 1. [YouTube Data API v3](youtube-api.md)
- **Purpose**: Upload 3D print timelapse videos to YouTube
- **API Type**: Official Google API
- **Authentication**: OAuth 2.0
- **Key Features**:
  - Video upload with metadata (title, description, tags)
  - Privacy settings (private, unlisted, public)
  - Analytics retrieval (views, likes, comments, shares)
  - Quota management (10,000 units/day)
  - Resumable uploads with progress tracking

### 2. [TikTok API](tiktok-api.md)
- **Purpose**: Upload 3D print timelapse videos to TikTok
- **API Type**: Official TikTok Content Posting API
- **Authentication**: OAuth 2.0
- **Key Features**:
  - Video upload via FILE_UPLOAD or PULL_FROM_URL
  - Caption/title with hashtags and mentions
  - Privacy levels (public, followers, private)
  - Status checking for async uploads
  - Direct post vs inbox upload modes

### 3. [Moonraker API](moonraker-api.md)
- **Purpose**: Communicate with 3D printers to discover and download timelapse videos
- **API Type**: Printer management API (Klipper/Moonraker)
- **Authentication**: Optional API key
- **Key Features**:
  - List available timelapse files
  - Download video files over HTTP
  - Monitor printer status
  - WebSocket notifications (optional)
  - Support for multiple printers

## API Comparison

| Feature | YouTube | TikTok | Moonraker |
|---------|---------|--------|-----------|
| **Authentication** | OAuth 2.0 | OAuth 2.0 | Optional API Key |
| **Video Upload** | Direct | Async (inbox/direct) | N/A (download only) |
| **Max File Size** | 256 GB | ~500 MB | N/A |
| **Analytics** | Rich (Analytics API) | Limited (Display API) | N/A |
| **Rate Limits** | Quota-based | Rate-limited | None |
| **Python SDK** | Yes (google-api-python-client) | No (HTTP requests) | No (HTTP requests) |
| **Token Lifetime** | 1 hour (refreshable) | 24 hours (refreshable) | N/A |
| **Approval Required** | No | Yes (for direct post) | N/A |

## Integration Architecture

```
┌─────────────────────────────────────────┐
│     Video Management System (Server)    │
│                                         │
│  ┌──────────────┐  ┌──────────────┐    │
│  │   YouTube    │  │    TikTok    │    │
│  │    API       │  │    API       │    │
│  └──────┬───────┘  └──────┬───────┘    │
│         │                  │             │
│         ▼                  ▼             │
│  ┌──────────────────────────────────┐   │
│  │      Upload Queue Service        │   │
│  └──────────────────────────────────┘   │
│         │                                │
│         ▼                                │
│  ┌──────────────────────────────────┐   │
│  │    Moonraker API Client          │   │
│  │    (Multiple Printers)           │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
         │
    Tailscale VPN
         │
┌─────────────────────────────────────────┐
│     3D Printer (Klipper/Moonraker)      │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │  Timelapse Directory (/timelapse)│   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

## Data Flow

### 1. Video Discovery
```
Server ──GET /server/files/list?root=timelapse──┐ Printer
        ◄───JSON file list───────────────────────┘
```

### 2. Video Download
```
Server ──GET /server/files/timelapse/{file}──┐ Printer
        ◄───Binary video data─────────────────┘
```

### 3. Platform Upload (YouTube)
```
Server ──POST /upload/youtube/v3/videos──┐ YouTube
        ◄───Video ID + metadata──────────┘
```

### 4. Platform Upload (TikTok)
```
Server ──POST /v2/post/publish/inbox/video/init/──┐ TikTok
        ◄───publish_id + upload_url───────────────┘
Server ──PUT {upload_url}─────────────────────────┐ TikTok
        ◄───Success confirmation──────────────────┘
```

### 5. Analytics Sync (YouTube)
```
Server ──GET /youtubeAnalytics/v2/reports──┐ YouTube
        ◄───Views, likes, comments─────────┘
```

### 6. Analytics Sync (TikTok)
```
Server ──POST /v2/video/query/──┐ TikTok
        ◄───Video metadata─────┘
```

## Configuration Requirements

### YouTube
1. Create project in Google Cloud Console
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials
4. Configure redirect URI
5. Store client_secrets.json securely

### TikTok
1. Create app at developers.tiktok.com
2. Add Login Kit and Content Posting products
3. Configure redirect URI
4. Request scopes: video.upload, user.info.basic
5. For direct post: Request video.publish + app audit
6. Verify domain (for PULL_FROM_URL method)

### Moonraker
1. Configure printer IP/URL in database
2. Set Moonraker port (default: 4409)
3. Add API key if Moonraker requires authentication
4. Ensure timelapse plugin is enabled
5. Verify Tailscale connectivity

## Authentication Storage

All platform credentials are stored in the database:

```sql
CREATE TABLE platform_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT UNIQUE NOT NULL,        -- 'youtube', 'tiktok'
    api_key TEXT,                          -- encrypted
    api_secret TEXT,                       -- encrypted
    access_token TEXT,                     -- encrypted
    refresh_token TEXT,                    -- encrypted
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

**Security Notes:**
- All tokens encrypted at rest
- Never commit credentials to repository
- Refresh tokens are long-lived
- Access tokens expire and auto-refresh

## Development Checklist

### Before Implementation
- [ ] Review all three API documentation files
- [ ] Set up developer accounts for YouTube and TikTok
- [ ] Configure test printers in database
- [ ] Verify Tailscale network connectivity
- [ ] Set up OAuth redirect endpoints

### During Implementation
- [ ] Implement Moonraker client for video discovery
- [ ] Implement YouTube upload service
- [ ] Implement TikTok upload service
- [ ] Add authentication flows for both platforms
- [ ] Implement analytics sync (midnight job)
- [ ] Add error handling and retry logic
- [ ] Test with small files first

### After Implementation
- [ ] Test OAuth flows end-to-end
- [ ] Verify video uploads to both platforms
- [ ] Check analytics data retrieval
- [ ] Monitor quota usage
- [ ] Set up logging and monitoring
- [ ] Document any workarounds or limitations

## Troubleshooting

### YouTube Issues
- **Quota exceeded**: Wait for midnight PT reset or request increase
- **Upload fails**: Check file size (max 256GB) and format (MP4 recommended)
- **Auth fails**: Verify scopes and redirect URI match configuration

### TikTok Issues
- **Upload pending**: TikTok processes async; check status endpoint
- **Domain not verified**: Verify domain in TikTok Developer Portal
- **Scope errors**: Re-authorize with correct scopes

### Moonraker Issues
- **Connection timeout**: Check Tailscale and printer power
- **404 errors**: File may have been deleted; trigger resync
- **Slow downloads**: Check network bandwidth; use smaller chunk sizes

## Additional Resources

### YouTube
- [API Console](https://console.cloud.google.com/)
- [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Python Quickstart](https://developers.google.com/youtube/v3/quickstart/python)

### TikTok
- [Developer Portal](https://developers.tiktok.com/)
- [API Status](https://status.tiktok.com/)
- [Migration Guide](https://developers.tiktok.com/doc/migration-guide)

### Moonraker
- [GitHub Repository](https://github.com/Arksine/moonraker)
- [Timelapse Plugin](https://github.com/mainsail-crew/moonraker-timelapse)
- [Klipper Documentation](https://www.klipper3d.org/)

## Notes

- All APIs are official and maintained by their respective platforms
- No third-party libraries or unofficial APIs are used
- Token refresh is handled automatically
- Quota/rate limits are monitored and respected
- Failed uploads are retried with exponential backoff
