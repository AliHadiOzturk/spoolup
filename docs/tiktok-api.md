# TikTok API Integration Guide

## Overview
This document details the integration with TikTok's official APIs for uploading 3D print timelapse videos and retrieving analytics data.

## Important Note
TikTok has multiple API products with different purposes. For video uploading, we use the **Content Posting API** (formerly Share Kit/Web Video Kit).

## API Products Overview

### 1. Content Posting API (Primary)
- **Purpose**: Upload videos directly to TikTok
- **Endpoint Base**: `https://open.tiktokapis.com/v2/`
- **Flow**: Upload to inbox or direct post
- **Best for**: Automated video uploads from applications

### 2. TikTok Login Kit
- **Purpose**: User authentication and authorization
- **Provides**: Access tokens for API calls
- **Required for**: Content Posting API access

### 3. Research API
- **Purpose**: Access public video data and analytics
- **Access**: Requires special application and approval
- **Use case**: Analytics and video metrics retrieval

### 4. Display API
- **Purpose**: Query video metadata and user info
- **Requires**: `video.list` scope
- **Use case**: Retrieving video details after upload

## Authentication

### OAuth 2.0 Flow
TikTok uses OAuth 2.0 for authentication. The flow is:
1. **Authorization Request**: Redirect user to TikTok's authorization page
2. **User Consent**: User grants permission to post videos
3. **Authorization Code**: TikTok redirects back with code
4. **Token Exchange**: Exchange code for access token
5. **Token Refresh**: Use refresh token to get new access tokens

### Required Scopes
For video upload functionality:
- `video.upload` - Upload videos to user's inbox
- `video.publish` - Direct post videos (requires audit)
- `user.info.basic` - Basic user information

### Authorization URL
```
https://www.tiktok.com/v2/auth/authorize/
  ?client_key={CLIENT_KEY}
  &redirect_uri={REDIRECT_URI}
  &scope=video.upload,user.info.basic
  &response_type=code
  &state={STATE}
```

### Token Exchange
```bash
curl --location --request POST 'https://open.tiktokapis.com/v2/oauth/token/' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode 'client_key=CLIENT_KEY' \
--data-urlencode 'client_secret=CLIENT_SECRET' \
--data-urlencode 'code=CODE' \
--data-urlencode 'grant_type=authorization_code' \
--data-urlencode 'redirect_uri=REDIRECT_URI'
```

### Response
```json
{
    "access_token": "act.example12345Example12345Example",
    "expires_in": 86400,
    "open_id": "afd97af1-b87b-48b9-ac98-410aghda5344",
    "refresh_expires_in": 31536000,
    "refresh_token": "rft.example12345Example12345Example",
    "scope": "user.info.basic,video.upload",
    "token_type": "Bearer"
}
```

### Token Refresh
```bash
curl --location --request POST 'https://open.tiktokapis.com/v2/oauth/token/' \
--header 'Content-Type: application/x-www-form-urlencoded' \
--data-urlencode 'client_key=CLIENT_KEY' \
--data-urlencode 'client_secret=CLIENT_SECRET' \
--data-urlencode 'grant_type=refresh_token' \
--data-urlencode 'refresh_token=REFRESH_TOKEN'
```

**Important**: The refresh token may change on refresh. Always save the new refresh token.

## Video Upload Methods

TikTok offers two upload methods:

### Method 1: FILE_UPLOAD (Recommended)
Upload video file directly to TikTok servers in chunks.

**Steps:**
1. Initialize upload with file metadata
2. Receive upload URL
3. Upload file chunks to provided URL
4. Check publish status

**Step 1: Initialize Upload**
```bash
curl --location 'https://open.tiktokapis.com/v2/post/publish/inbox/video/init/' \
--header 'Authorization: Bearer {ACCESS_TOKEN}' \
--header 'Content-Type: application/json' \
--data '{
    "source_info": {
        "source": "FILE_UPLOAD",
        "video_size": 30567100,
        "chunk_size": 30567100,
        "total_chunk_count": 1
    }
}'
```

**Response:**
```json
{
    "data": {
        "publish_id": "v_inbox_file~v2.123456789",
        "upload_url": "https://open-upload.tiktokapis.com/video/?upload_id=12345&upload_token=Xza123"
    },
    "error": {
        "code": "ok",
        "message": "",
        "log_id": "202210112248442CB9319E1FB30C1073F3"
    }
}
```

**Step 2: Upload File**
```bash
curl --location --request PUT '{UPLOAD_URL}' \
--header 'Content-Type: video/mp4' \
--data-binary '@/path/to/video.mp4'
```

**Step 3: Check Status**
```bash
curl --location 'https://open.tiktokapis.com/v2/post/publish/status/fetch/' \
--header 'Authorization: Bearer {ACCESS_TOKEN}' \
--header 'Content-Type: application/json' \
--data '{
    "publish_id": "v_inbox_file~v2.123456789"
}'
```

### Method 2: PULL_FROM_URL
Provide a public URL for TikTok to fetch the video.

**Requirements:**
- Video URL must be publicly accessible
- Domain must be verified in TikTok Developer Portal
- Video must be hosted on your domain

**Request:**
```bash
curl --location 'https://open.tiktokapis.com/v2/post/publish/inbox/video/init/' \
--header 'Authorization: Bearer {ACCESS_TOKEN}' \
--header 'Content-Type: application/json' \
--data '{
    "source_info": {
        "source": "PULL_FROM_URL",
        "video_url": "https://your-verified-domain.com/video.mp4"
    }
}'
```

## Direct Post vs Inbox Upload

### Inbox Upload (video.upload scope)
- Video appears in user's TikTok inbox
- User must manually review and publish
- No audit required
- Available immediately

### Direct Post (video.publish scope)
- Video posts directly to user's account
- No manual review required
- **Requires app audit** by TikTok
- Content from unaudited clients is restricted to private viewing
- Recommended for fully automated workflows

## Video Metadata

### Upload Parameters
```json
{
    "post_info": {
        "title": "3D Print Timelapse #3DPrinting #Klipper",
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "disable_duet": false,
        "disable_comment": false,
        "disable_stitch": false,
        "video_cover_timestamp_ms": 1000,
        "brand_content_toggle": false,
        "is_aigc": false
    },
    "source_info": {
        "source": "FILE_UPLOAD",
        "video_size": 30567100,
        "chunk_size": 30567100,
        "total_chunk_count": 1
    }
}
```

### Privacy Levels
| Level | Description |
|-------|-------------|
| PUBLIC_TO_EVERYONE | Visible to everyone |
| MUTUAL_FOLLOW_FRIENDS | Only mutual followers |
| FOLLOWER_OF_CREATOR | Only followers |
| SELF_ONLY | Private (only creator) |

### Title/Caption
- Maximum length: 2200 UTF-16 characters
- Supports hashtags (#) and mentions (@)
- Automatically parsed by TikTok

## Checking Upload Status

### Endpoint
```
POST /v2/post/publish/status/fetch/
```

### Request
```bash
curl --location 'https://open.tiktokapis.com/v2/post/publish/status/fetch/' \
--header 'Authorization: Bearer {ACCESS_TOKEN}' \
--header 'Content-Type: application/json' \
--data '{
    "publish_id": "v_inbox_file~v2.123456789"
}'
```

### Possible Statuses
- `PUBLISH_PENDING` - Upload in progress
- `PUBLISH_SUCCESS` - Upload successful
- `PUBLISH_FAILED` - Upload failed

## Querying Video Data

### Display API
Query uploaded videos to get metadata and engagement metrics.

### Request
```bash
curl -L -X POST 'https://open.tiktokapis.com/v2/video/query/?fields=id,cover_image_url,embed_link,title' \
-H 'Authorization: Bearer {ACCESS_TOKEN}' \
-H 'Content-Type: application/json' \
--data-raw '{
    "filters": {
        "video_ids": ["7077642457847994444"]
    }
}'
```

## Research API for Analytics

### Access Requirements
The Research API requires special approval from TikTok:
- Must be affiliated with a non-profit research institution
- Application process required
- Not suitable for general analytics

### Alternative: Display API
For basic analytics (views, likes, comments), use the Display API with video.list scope after uploading.

## Video Requirements

### Supported Formats
- MP4 (recommended)
- MOV
- MPEG
- AVI

### Specifications
- Duration: 15 seconds to 10 minutes (standard)
- Resolution: Minimum 720x1280 (portrait recommended)
- Aspect ratio: 9:16 (vertical) recommended
- File size: Up to 500MB (varies by region)
- Frame rate: 30fps or 60fps

### Recommendations for 3D Printing Timelapse
- Use vertical format (9:16) for best engagement
- Keep duration under 60 seconds for higher completion rate
- Add music or trending sounds
- Include hashtags: #3DPrinting #Timelapse #Klipper #Maker

## Error Handling

### Common Errors
| Error Code | Description | Solution |
|------------|-------------|----------|
| access_token_invalid | Token expired or invalid | Refresh token |
| invalid_scope | Scope not authorized | Re-authorize with correct scopes |
| rate_limit | Too many requests | Implement rate limiting |
| video_size_too_large | File exceeds size limit | Compress video or split into parts |
| domain_not_verified | URL domain not verified | Verify domain in Developer Portal |
| publish_failed | Upload processing failed | Retry upload |

### Error Response Format
```json
{
    "error": {
        "code": "error_code",
        "message": "Human readable description",
        "log_id": "202210112248442CB9319E1FB30C1073F3"
    }
}
```

## Quota and Rate Limits

### Default Limits
- Upload: Varies by app tier
- API calls: Rate-limited per endpoint
- Token refresh: Unlimited (within reason)

### Best Practices
- Implement exponential backoff for retries
- Cache access tokens until near expiry
- Batch operations when possible
- Monitor rate limit headers in responses

## Implementation Notes

### Dependencies
```
requests>=2.31.0
```

No official Python SDK required. Use standard HTTP requests.

### File Storage
- Store client_key and client_secret securely
- Encrypt access_token and refresh_token in database
- Refresh tokens valid for 365 days (may change)

### Webhook Support
TikTok does not currently support webhooks for upload status. Must poll for status.

## App Configuration

### Developer Portal Setup
1. Create app at https://developers.tiktok.com/
2. Add products: Login Kit, Content Posting
3. Configure redirect URI
4. Request scopes: video.upload, user.info.basic
5. For direct post: Request video.publish scope + app audit
6. For PULL_FROM_URL: Verify domain ownership

### Approval Process
- Basic upload (inbox): Immediate
- Direct post: Requires audit (1-2 weeks)
- Research API: Requires research application

## Testing

### Test Environment
- Use sandbox/test accounts
- Set privacy to SELF_ONLY during testing
- Monitor upload status after each test
- Check TikTok app dashboard for errors

### Validation Checklist
- [ ] OAuth flow works correctly
- [ ] Token refresh functions properly
- [ ] File upload completes successfully
- [ ] Status checking returns correct state
- [ ] Error handling covers edge cases

## Limitations and Considerations

### Current Limitations
- No official Python SDK (use HTTP requests)
- No webhook notifications for upload status
- Research API requires special approval
- Direct post requires app audit
- Domain verification required for URL-based uploads

### Compared to YouTube
- More complex OAuth flow
- No direct video update after upload
- Limited analytics without Research API
- Inbox upload requires user action
- Better mobile/vertical video support

## Migration from Legacy APIs

### Old Share Kit API
```
POST https://open-api.tiktok.com/share/video/upload/
```
**Status**: Deprecated, migrate to Content Posting API

### New Content Posting API
```
POST https://open.tiktokapis.com/v2/post/publish/inbox/video/init/
```
**Status**: Current, actively maintained

## References
- [TikTok for Developers](https://developers.tiktok.com/)
- [Content Posting API Docs](https://developers.tiktok.com/doc/content-posting-api-get-started)
- [Login Kit Docs](https://developers.tiktok.com/doc/login-kit-web)
- [OAuth User Access Token](https://developers.tiktok.com/doc/oauth-user-access-token-management)
- [Video Upload Reference](https://developers.tiktok.com/doc/content-posting-api-reference-upload-video)
- [Display API Docs](https://developers.tiktok.com/doc/display-api-get-started)
