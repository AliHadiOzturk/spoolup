# Short-Form Video Standards: YouTube Shorts vs TikTok

## Overview
This document outlines the technical specifications, limitations, and best practices for uploading short-form videos (YouTube Shorts and TikTok) from 3D printer timelapse footage.

## Platform Specifications Comparison

### YouTube Shorts

#### Technical Requirements
| Specification | Requirement | Notes |
|---------------|-------------|-------|
| **Duration** | 15 seconds to 60 seconds | Maximum 60 seconds for Shorts feed |
| **Aspect Ratio** | 9:16 (vertical) | Must be square or taller (1:1 to 9:16) |
| **Resolution** | 1920x1080 or higher | Vertical format: 1080x1920 recommended |
| **File Size** | Up to 256 GB | No practical limit for most videos |
| **Frame Rate** | 24-60 FPS | 30 FPS recommended |
| **Format** | MP4 (H.264), MOV, AVI | MP4 strongly recommended |
| **Audio** | Required | Shorts without audio get less distribution |

#### Content Requirements
- **Title**: Max 100 characters
- **Description**: Max 5,000 characters  
- **Tags**: Up to 500 characters total
- **Hashtags**: Use #Shorts for better discoverability
- **Category**: 28 (Science & Technology) recommended
- **Privacy**: Public for Shorts feed visibility

#### API-Specific Notes
- Upload via standard `videos.insert` endpoint
- Set `shorts` in title or description for Shorts feed
- Quota cost: 100 units per upload
- Processing time: Usually under 5 minutes

### TikTok

#### Technical Requirements
| Specification | Requirement | Notes |
|---------------|-------------|-------|
| **Duration** | 15 seconds to 10 minutes | Shorts typically 15-60 seconds |
| **Aspect Ratio** | 9:16 (vertical) | Between 1:2.2 and 2.2:1 accepted |
| **Resolution** | Minimum 540x960 | 1080x1920 recommended |
| **File Size** | Maximum 4 GB | Via Content Posting API |
| **Frame Rate** | 23-60 FPS | 30 FPS recommended |
| **Format** | MP4 (H.264 recommended), MOV, WebM | MP4 strongly recommended |
| **Audio** | Optional | Can add trending sounds later |

#### Content Requirements
- **Title/Caption**: Max 2,200 UTF-16 characters
- **Hashtags**: Use #3DPrinting #Timelapse #Klipper
- **Mentions**: Support @username mentions
- **Privacy Levels**: PUBLIC_TO_EVERYONE, FOLLOWER_OF_CREATOR, SELF_ONLY
- **Duet/Stitch**: Can disable/enable

#### API-Specific Notes
- Two upload methods: FILE_UPLOAD and PULL_FROM_URL
- FILE_UPLOAD: Initialize → Get upload_url → PUT chunks → Check status
- PULL_FROM_URL: Requires verified domain
- Async processing: Must poll for status
- Quota: Rate-limited per app

## 3D Printing Timelapse Considerations

### Video Duration Challenges

**Problem**: 3D print timelapses are often 30 seconds to 5 minutes, depending on print duration and frame capture interval.

**Solutions**:
1. **Speed up footage**: Use higher playback rate (e.g., 60 FPS timelapse)
2. **Trim to best segment**: Select most interesting 30-60 second portion
3. **Combine multiple angles**: If available, switch between camera angles
4. **Add intro/outro**: Brief text overlay showing print info

### Aspect Ratio Conversion

**Problem**: Webcam footage is typically 16:9 (1920x1080), but Shorts require 9:16.

**Solutions**:
1. **Crop and pan**: Focus on the print bed, follow the print head
2. **Add sidebars**: Show print stats (temperature, progress %) on sides
3. **Split screen**: Show multiple camera angles stacked vertically
4. **Zoom and center**: Crop to center of print bed

### Resolution and Quality

**Recommended Settings**:
- **Input**: Capture at highest available resolution
- **Output**: 1080x1920 (9:16) for both platforms
- **Bitrate**: 8-15 Mbps for crisp timelapse details
- **Frame Rate**: 30 FPS (smooth playback)

### File Size Optimization

**For TikTok** (stricter limits):
- Target under 100 MB for faster uploads
- Use H.264 codec with CRF 23
- Remove unnecessary audio tracks
- Optimize for mobile viewing

**For YouTube**:
- Can handle larger files
- Still optimize for faster upload/processing
- Use MP4 container for best compatibility

## Implementation Strategy

### Video Processing Pipeline

```
Raw Timelapse (MP4, 16:9)
    ↓
Download from Printer (Moonraker API)
    ↓
Extract Metadata (ffprobe)
    ↓
Video Processing (FFmpeg)
    ├── Crop/Resize to 9:16
    ├── Trim to 60 seconds max
    ├── Add text overlays (optional)
    └── Optimize bitrate
    ↓
Platform-Specific Upload
    ├── YouTube: Direct upload via API
    └── TikTok: Chunked upload or URL pull
```

### FFmpeg Processing Commands

#### Convert to YouTube Shorts Format
```bash
ffmpeg -i input.mp4 \
  -vf "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2, fps=30" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  output_shorts.mp4
```

#### Convert to TikTok Format (with sidebars)
```bash
ffmpeg -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease, \
       pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black, \
       fps=30, \
       drawtext=text='Temp: 200°C':x=20:y=20:fontsize=24:fontcolor=white" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  output_tiktok.mp4
```

#### Speed up long timelapse
```bash
# Speed up 2x (useful for long prints)
ffmpeg -i input.mp4 \
  -vf "setpts=0.5*PTS, crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2, fps=30" \
  -an \
  -c:v libx264 -preset fast -crf 23 \
  output_fast.mp4
```

## Platform-Specific Upload Logic

### YouTube Shorts Upload
```python
body = {
    'snippet': {
        'title': f'3D Print Timelapse: {filename} #Shorts',
        'description': f'3D printing timelapse using Klipper\n#Shorts #3DPrinting #Klipper #Timelapse',
        'tags': ['Shorts', '3D Printing', 'Klipper', 'Timelapse', 'Creality'],
        'categoryId': '28'  # Science & Technology
    },
    'status': {
        'privacyStatus': 'public',
        'selfDeclaredMadeForKids': False
    }
}

# Upload via Data API v3
request = youtube.videos().insert(
    part='snippet,status',
    body=body,
    media_body=MediaFileUpload(processed_file, resumable=True)
)
```

### TikTok Upload
```python
# Step 1: Initialize upload
init_data = {
    "source_info": {
        "source": "FILE_UPLOAD",
        "video_size": file_size,
        "chunk_size": chunk_size,
        "total_chunk_count": total_chunks
    },
    "post_info": {
        "title": f"3D Print Timelapse 🖨️✨ #3DPrinting #Klipper #Timelapse",
        "privacy_level": "PUBLIC_TO_EVERYONE",
        "disable_duet": False,
        "disable_stitch": False,
        "disable_comment": False,
        "brand_content_toggle": False
    }
}

# Step 2: Upload chunks
# Step 3: Check status
```

## Limitations and Constraints

### YouTube Shorts Limitations
- **Duration cap**: 60 seconds max for Shorts feed
- **API quota**: 10,000 units/day (100 per upload)
- **Processing time**: 1-5 minutes typical
- **Private uploads**: Unverified API projects default to private
- **Monetization**: Requires Partner Program (1,000 subs, 4,000 watch hours)

### TikTok Limitations
- **File size**: 4 GB max (but 50-100 MB recommended)
- **Upload method**: FILE_UPLOAD requires chunking for files > 64 MB
- **Processing time**: Async, may take several minutes
- **Direct post**: Requires app audit approval
- **Inbox upload**: User must manually publish
- **Rate limits**: Stricter than YouTube
- **Research API**: Requires special approval for analytics

### 3D Print Specific Challenges
- **Video length**: Long prints = long timelapses, need speed-up
- **Camera angle**: Fixed webcam not ideal for vertical format
- **Lighting**: Print bed lighting may not be optimal
- **Details**: Fine print details may not show well in 9:16 crop
- **Audio**: Timelapses typically silent, need to add music/sound

## Best Practices

### For Maximum Engagement
1. **Hook in first 3 seconds**: Show print progress or interesting layer
2. **Show before/after**: Start with empty bed, end with finished print
3. **Add music**: Use trending sounds (TikTok) or YouTube audio library
4. **Text overlays**: Show print time, material, temperature
5. **Hashtags**: #3DPrinting #Klipper #Timelapse #Maker #Shorts
6. **Post consistently**: Regular timelapse uploads build audience

### Technical Best Practices
1. **Pre-process videos**: Convert to 9:16 before upload
2. **Optimize file size**: Balance quality vs upload speed
3. **Use consistent branding**: Same intro/outro style
4. **Monitor metrics**: Track views, likes, comments for each platform
5. **A/B test**: Try different formats (crop vs zoom vs split-screen)

### Automation Considerations
1. **Auto-trim**: Set max duration (60 sec for Shorts)
2. **Auto-format**: Convert all videos to 9:16
3. **Auto-hashtag**: Add platform-specific hashtags
4. **Auto-schedule**: Post during peak hours
5. **Auto-analytics**: Sync metrics daily

## Quality Checklist

Before uploading, verify:
- [ ] Duration ≤ 60 seconds (for Shorts feed)
- [ ] Aspect ratio is 9:16 (vertical)
- [ ] Resolution at least 1080x1920
- [ ] File size under platform limits
- [ ] Title includes #Shorts (YouTube)
- [ ] Description has relevant hashtags
- [ ] Privacy setting is correct
- [ ] Thumbnail is engaging (if supported)
- [ ] Audio is added (if needed)
- [ ] Text overlays are readable

## Platform Differences Summary

| Feature | YouTube Shorts | TikTok |
|---------|---------------|--------|
| Max Duration | 60 seconds | 10 minutes (3 min typical) |
| File Size | 256 GB | 4 GB |
| Aspect Ratio | 9:16 (or 1:1) | 9:16 |
| Upload Method | Direct API | Async (chunks/URL) |
| Processing | Synchronous | Asynchronous |
| Analytics | Rich (Analytics API) | Limited (Display API) |
| Monetization | Partner Program | Creator Fund (varies) |
| Audience | Broader, older | Younger, trend-focused |
| Discovery | Shorts feed, search | For You Page |
| Audio | YouTube library | Trending sounds |

## References
- [YouTube Shorts Creation](https://www.youtube.com/creators/shorts/)
- [YouTube Data API v3](https://developers.google.com/youtube/v3)
- [TikTok Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started)
- [TikTok Media Transfer Guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
