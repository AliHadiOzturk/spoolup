# YouTube Data API v3 Integration Guide

## Overview
This document details the integration with YouTube Data API v3 for uploading 3D print timelapse videos and retrieving analytics data.

## API Reference
- **Official Documentation**: https://developers.google.com/youtube/v3
- **Analytics API**: https://developers.google.com/youtube/analytics

## Authentication

### OAuth 2.0 Flow
YouTube Data API v3 uses OAuth 2.0 for authentication. The application must obtain user consent to upload videos on their behalf.

### Required Scopes
```python
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",      # Upload videos
    "https://www.googleapis.com/auth/youtube.force-ssl",   # Full access with SSL
    "https://www.googleapis.com/auth/youtube.readonly",    # Read analytics
]
```

### Authentication Flow
1. **Authorization Request**: Redirect user to Google's OAuth 2.0 server
2. **User Consent**: User grants permission to upload videos
3. **Authorization Code**: Google redirects back with authorization code
4. **Token Exchange**: Exchange code for access token and refresh token
5. **Token Storage**: Store credentials (access_token, refresh_token, expires_at)

### Python Implementation
```python
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Step 1: Create OAuth flow
flow = Flow.from_client_secrets_file(
    'client_secrets.json',
    scopes=['https://www.googleapis.com/auth/youtube.upload']
)

# Step 2: Generate authorization URL
flow.redirect_uri = 'https://your-app.com/oauth2callback'
auth_url, _ = flow.authorization_url(prompt='consent')

# Step 3: After user authorizes, fetch token
flow.fetch_token(code=authorization_code)
credentials = flow.credentials

# Step 4: Build YouTube service
youtube = build('youtube', 'v3', credentials=credentials)
```

### Token Refresh
Access tokens expire after 1 hour. Use refresh token to obtain new access token:
```python
from google.auth.transport.requests import Request

if credentials.expired and credentials.refresh_token:
    credentials.refresh(Request())
    # Save updated credentials
```

## Video Upload

### Endpoint
```
POST https://www.googleapis.com/upload/youtube/v3/videos
```

### Upload Process
1. **Prepare metadata** (title, description, tags, privacy status)
2. **Create video resource** with snippet and status
3. **Upload file** using resumable upload
4. **Handle response** (video ID, status)

### Request Structure
```python
def upload_video(youtube, file_path, title, description, tags, privacy_status='private'):
    body = {
        'snippet': {
            'title': title,                    # Max 100 characters
            'description': description,         # Max 5000 characters
            'tags': tags,                       # List of strings
            'categoryId': '28'                  # 28 = Science & Technology
        },
        'status': {
            'privacyStatus': privacy_status     # 'private', 'public', 'unlisted'
        }
    }
    
    # Create upload request with resumable upload
    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
    )
    
    # Execute upload with progress tracking
    response = None
    while response is None:
        status, response = insert_request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")
    
    return response['id']  # Returns video ID
```

### Upload Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| part | string | Yes | Comma-separated list: snippet, status, contentDetails |
| body.snippet.title | string | Yes | Video title (max 100 chars) |
| body.snippet.description | string | No | Video description (max 5000 chars) |
| body.snippet.tags | array | No | List of keywords |
| body.snippet.categoryId | string | Yes | Video category ID |
| body.status.privacyStatus | string | Yes | 'private', 'public', or 'unlisted' |
| media_body | file | Yes | Video file to upload |

### Supported Video Formats
- MP4 (recommended)
- AVI
- MKV
- MOV
- WMV
- FLV
- 3GPP
- WebM

### Video Requirements
- Maximum file size: 256 GB or 12 hours (whichever is less)
- Recommended resolutions: 1080p, 720p
- Aspect ratio: 16:9 recommended

## Quota Management

### Default Quota
- **Daily limit**: 10,000 quota units per day
- **Reset**: Midnight Pacific Time (PT)

### Quota Costs
| Operation | Cost (units) |
|-----------|-------------|
| Video upload (insert) | 100 |
| Video list | 1 |
| Video update | 50 |
| Video delete | 50 |
| Search | 100 |
| Channel list | 1 |
| Analytics query | 1 |

### Optimization Strategies
- Batch operations when possible
- Cache video metadata to avoid repeated API calls
- Use `part` parameter to request only needed fields
- Monitor quota usage and request increases if needed

## Analytics Retrieval

### YouTube Analytics API
Retrieve video performance metrics including views, likes, comments, and shares.

### Endpoint
```
GET https://youtubeanalytics.googleapis.com/v2/reports
```

### Query Parameters
```python
def get_video_analytics(youtube_analytics, video_id, start_date, end_date):
    request = youtube_analytics.reports().query(
        ids='channel==MINE',
        startDate=start_date,      # Format: YYYY-MM-DD
        endDate=end_date,          # Format: YYYY-MM-DD
        metrics='views,likes,comments,shares',
        dimensions='video',
        filters=f'video=={video_id}'
    )
    response = request.execute()
    return response
```

### Available Metrics
| Metric | Description |
|--------|-------------|
| views | Number of views |
| likes | Number of likes |
| dislikes | Number of dislikes (deprecated) |
| comments | Number of comments |
| shares | Number of shares |
| estimatedMinutesWatched | Estimated watch time |
| averageViewDuration | Average view duration |
| subscribersGained | New subscribers |

### Response Format
```json
{
  "kind": "youtubeAnalytics#resultTable",
  "columnHeaders": [
    {"name": "views", "columnType": "METRIC", "dataType": "INTEGER"},
    {"name": "likes", "columnType": "METRIC", "dataType": "INTEGER"},
    {"name": "comments", "columnType": "METRIC", "dataType": "INTEGER"}
  ],
  "rows": [
    [1234, 56, 12]
  ]
}
```

## Error Handling

### Common Errors
| Error Code | HTTP Status | Description | Solution |
|------------|-------------|-------------|----------|
| invalidPart | 400 | Invalid part parameter | Use valid parts: snippet, status, contentDetails |
| forbidden | 403 | Insufficient permissions | Check OAuth scopes and channel permissions |
| quotaExceeded | 403 | Quota limit reached | Wait for quota reset or request increase |
| uploadLimitExceeded | 400 | Daily upload limit | YouTube has daily upload limits per channel |
| badRequest | 400 | Malformed request | Check request parameters |

### Retry Strategy
```python
RETRIABLE_EXCEPTIONS = (
    httplib2.HttpLib2Error, IOError, 
    httplib.NotConnected, httplib.IncompleteRead
)
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# Implement exponential backoff
for attempt in range(max_retries):
    try:
        response = upload_request.execute()
        break
    except Exception as e:
        if attempt < max_retries - 1:
            sleep_time = 2 ** attempt
            time.sleep(sleep_time)
        else:
            raise
```

## Implementation Notes

### Dependencies
```
google-api-python-client>=2.100.0
google-auth-httplib2>=0.1.1
google-auth-oauthlib>=1.0.0
```

### File Storage
- Store `client_secrets.json` securely (never commit to repo)
- Store tokens in database (encrypted)
- Refresh tokens are long-lived (until revoked by user)

### Privacy Settings
- **private**: Only visible to uploader
- **unlisted**: Accessible via direct link
- **public**: Visible to everyone

### Recommended Settings for 3D Printing
- Category: 28 (Science & Technology)
- Privacy: unlisted (for testing), public (for sharing)
- Tags: ["3D printing", "timelapse", "klipper", "creality"]

## API Status and Limitations

### Current Status
- **Active**: YouTube Data API v3 is fully supported
- **No deprecation**: Not scheduled for deprecation
- **Rate limits**: Quota-based (10,000 units/day)

### Known Limitations
- Maximum 50 tags per video
- Description max 5000 characters
- Title max 100 characters
- Upload may take several minutes for large files
- Processing time varies based on video length and resolution

## Testing

### Test Credentials
- Create test project in Google Cloud Console
- Enable YouTube Data API v3
- Create OAuth 2.0 credentials
- Add test users before app verification

### Sandbox Mode
- Use "private" privacy status for testing
- Create separate test channel
- Monitor quota usage in Google Cloud Console

## References
- [YouTube Data API Overview](https://developers.google.com/youtube/v3/getting-started)
- [Uploading Videos](https://developers.google.com/youtube/v3/guides/uploading_a_video)
- [OAuth 2.0 for Server-Side Web Apps](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps)
- [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Error Documentation](https://developers.google.com/youtube/v3/docs/errors)
