# TikTok App Review Submission - SpoolUp

## App Description (Publicly Visible)

SpoolUp is a video management and publishing platform for 3D printing enthusiasts. The app connects to 3D printers running Klipper firmware via the Moonraker API to access timelapse videos that are already recorded by the printer's built-in timelapse system. Users can then process these videos (convert to vertical format for short-form platforms) and publish them to TikTok, YouTube, and Instagram from a single web-based dashboard.

## Submission Reason / Detailed App Description

SpoolUp is a specialized content management and publishing tool for the 3D printing community. The application runs on a user's local network (or self-hosted server) and performs the following functions:

1. **Video Discovery**: Connects to 3D printers via the Moonraker/Klipper API to discover and access timelapse videos that have already been recorded by the printer's built-in timelapse camera system. SpoolUp does not record videos itself - it only accesses existing timelapse files stored on the printer.

2. **Video Processing**: Processes the discovered timelapse footage using FFmpeg - including format conversion from horizontal 16:9 to vertical 9:16 aspect ratio optimized for short-form platforms like TikTok, applying speed adjustments, adding text overlays, and adding audio tracks.

3. **Multi-Platform Publishing**: Provides a unified dashboard where users can queue their processed 3D printing timelapse videos for upload to TikTok, YouTube Shorts, and Instagram with custom titles, descriptions, hashtags, and privacy settings.

4. **Upload Queue Management**: Manages a background upload queue with retry logic, status polling, and error handling for each platform.

5. **Analytics Tracking**: Retrieves video performance metrics (views, likes, comments, shares) from connected platforms to help creators understand which content performs best.

## Scopes Requested and Data Usage

### `video.publish`
- **What it enables**: Direct video upload to a user's TikTok account via TikTok's Content Posting API.
- **How the data is used**: 
  - Upload processed 3D printing timelapse videos (which were originally recorded by the user's 3D printer) directly to the user's TikTok account.
  - Support both draft uploads (saved to inbox for manual review) and direct publishing.
  - Set video metadata: title, description/caption, privacy level (public, followers-only, or private), and interaction settings (enable/disable comments, duets, stitches).
  - Poll upload status to confirm successful processing.
  - List previously uploaded videos and query their metadata.
  - Retrieve video analytics (view count, like count, comment count, share count) for performance tracking in the SpoolUp dashboard.
- **Data stored**: Video file content, title, description, privacy settings, and upload status are temporarily processed during the upload workflow. No video content is stored permanently on SpoolUp servers; videos are streamed directly from the user's local storage to TikTok's servers.

### `user.info.basic`
- **What it enables**: Access to basic TikTok account information for the authenticated user.
- **How the data is used**:
  - Retrieve the user's display name and avatar to show in the SpoolUp dashboard connection status, confirming which TikTok account is linked.
  - Fetch follower count, following count, and total likes count to display in the analytics section alongside video performance data.
  - Obtain the user's unique Open ID for associating the TikTok connection with the correct user account in the SpoolUp system.
- **Data stored**: Only the user's display name, avatar URL, and follower count are cached briefly in the local database for dashboard display. No personal data is shared with third parties.

## User Workflow

1. User connects their TikTok account via OAuth 2.0 with PKCE from the SpoolUp dashboard.
2. User connects their 3D printer(s) to SpoolUp via the Moonraker API.
3. SpoolUp discovers existing timelapse videos already recorded by the printer's camera system.
4. The user selects a timelapse video in SpoolUp, processes it (convert to 9:16 format, add audio, etc.), then adds a title, description, and hashtags, and chooses privacy settings.
5. SpoolUp initializes a chunked video upload to TikTok, uploads the file in segments, and polls for completion status.
6. The video appears on the user's TikTok account (either as a draft or published directly, depending on the app's audit status).
7. SpoolUp periodically retrieves video analytics to display performance metrics in the dashboard.

## Technical Details

- **Platform**: Self-hosted web application (runs on user's local network or server)
- **OAuth Flow**: Authorization Code with PKCE (state parameter and code_verifier)
- **Token Storage**: Access tokens and refresh tokens are stored encrypted on the user's local machine, never on remote servers
- **Video Upload Method**: File Upload via chunked transfer to TikTok's upload servers
- **Rate Limiting**: Exponential backoff implemented for API rate limits
- **Video Source**: Timelapse videos are recorded by the 3D printer's built-in camera/timelapse system (Moonraker/Klipper), not by SpoolUp itself

## Privacy and Security

- All user data remains on the user's self-hosted instance; SpoolUp does not operate centralized servers.
- TikTok access tokens are stored locally and encrypted.
- Videos are uploaded directly from the user's local storage to TikTok without intermediary storage.
- Users can revoke TikTok access at any time via their TikTok account settings.
- Full privacy policy and terms of service are available at: https://spoolup.alihadiozturk.com/privacy-policy.html and https://spoolup.alihadiozturk.com/terms-of-service.html

## Category

Content Creation / Publishing Tool

## Website

https://spoolup.alihadiozturk.com

## Platform

Web Application (self-hosted)

## Use Case

Video management and publishing for 3D printing content creators
