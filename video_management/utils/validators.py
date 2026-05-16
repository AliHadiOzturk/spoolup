"""Input validation and sanitization utilities."""

import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def validate_video_file(path: str) -> Dict[str, any]:
    """Validate a video file exists and is valid.
    
    Returns:
        Dict with 'valid' (bool), 'size' (int), 'error' (Optional[str])
    """
    if not os.path.exists(path):
        return {"valid": False, "size": 0, "error": "File not found"}
    
    size = os.path.getsize(path)
    if size == 0:
        return {"valid": False, "size": 0, "error": "File is empty"}
    
    if size > 2 * 1024 * 1024 * 1024:  # 2GB max
        return {"valid": False, "size": size, "error": "File exceeds 2GB limit"}
    
    ext = os.path.splitext(path)[1].lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        return {"valid": False, "size": size, "error": f"Unsupported format: {ext}"}
    
    return {"valid": True, "size": size, "error": None}


def validate_image_file(path: str) -> Dict[str, any]:
    """Validate an image file for thumbnails.
    
    Returns:
        Dict with 'valid' (bool), 'size' (int), 'error' (Optional[str])
    """
    if not os.path.exists(path):
        return {"valid": False, "size": 0, "error": "File not found"}
    
    size = os.path.getsize(path)
    if size == 0:
        return {"valid": False, "size": 0, "error": "File is empty"}
    
    if size > 10 * 1024 * 1024:  # 10MB max for thumbnails
        return {"valid": False, "size": size, "error": "Thumbnail exceeds 10MB limit"}
    
    ext = os.path.splitext(path)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        return {"valid": False, "size": size, "error": f"Unsupported image format: {ext}"}
    
    return {"valid": True, "size": size, "error": None}


def validate_tags(tags: List[str]) -> Dict[str, any]:
    """Validate YouTube/TikTok tags.
    
    Rules:
    - Max 15 tags
    - Each tag max 30 characters
    - No special characters except spaces, hyphens, underscores
    
    Returns:
        Dict with 'valid' (bool), 'tags' (List[str]), 'error' (Optional[str])
    """
    if not tags:
        return {"valid": True, "tags": [], "error": None}
    
    if len(tags) > 15:
        return {"valid": False, "tags": tags, "error": "Maximum 15 tags allowed"}
    
    cleaned = []
    for tag in tags:
        tag = tag.strip()
        if len(tag) > 30:
            return {"valid": False, "tags": tags, "error": f"Tag too long (max 30 chars): {tag}"}
        if not re.match(r"^[\w\s\-]+$", tag):
            return {"valid": False, "tags": tags, "error": f"Invalid characters in tag: {tag}"}
        cleaned.append(tag)
    
    return {"valid": True, "tags": cleaned, "error": None}


def validate_youtube_title(title: str) -> Dict[str, any]:
    """Validate YouTube video title.
    
    Returns:
        Dict with 'valid' (bool), 'title' (str), 'error' (Optional[str])
    """
    if not title or not title.strip():
        return {"valid": False, "title": title, "error": "Title is required"}
    
    title = title.strip()
    if len(title) > 100:
        return {"valid": False, "title": title, "error": "Title exceeds 100 characters"}
    
    return {"valid": True, "title": title, "error": None}


def validate_youtube_description(description: str) -> Dict[str, any]:
    """Validate YouTube video description.
    
    Returns:
        Dict with 'valid' (bool), 'description' (str), 'error' (Optional[str])
    """
    if not description:
        return {"valid": True, "description": "", "error": None}
    
    if len(description) > 5000:
        return {"valid": False, "description": description, "error": "Description exceeds 5000 characters"}
    
    return {"valid": True, "description": description, "error": None}


def sanitize_html(text: str) -> str:
    """Remove HTML tags to prevent XSS.
    
    Args:
        text: Input text that may contain HTML
        
    Returns:
        Clean text with HTML tags removed
    """
    if not text:
        return ""
    
    # Remove HTML tags
    clean = re.sub(r"</?[^>>]+>", "", text)
    
    # Escape HTML entities
    clean = clean.replace("&", "&amp;")
    clean = clean.replace("<", "&lt;")
    clean = clean.replace(">", "&gt;")
    clean = clean.replace('"', "&quot;")
    clean = clean.replace("'", "&#x27;")
    
    return clean


def validate_filename(filename: str) -> Dict[str, any]:
    """Validate filename to prevent path traversal attacks.
    
    Returns:
        Dict with 'valid' (bool), 'filename' (str), 'error' (Optional[str])
    """
    if not filename:
        return {"valid": False, "filename": filename, "error": "Filename is required"}
    
    # Remove path traversal attempts
    filename = os.path.basename(filename)
    
    # Remove null bytes
    filename = filename.replace("\x00", "")
    
    # Check for invalid characters
    invalid_chars = re.findall(r"[<>:\"/\\|?*]", filename)
    if invalid_chars:
        return {"valid": False, "filename": filename, "error": f"Invalid characters in filename: {invalid_chars}"}
    
    # Check length
    if len(filename) > 255:
        return {"valid": False, "filename": filename, "error": "Filename exceeds 255 characters"}
    
    return {"valid": True, "filename": filename, "error": None}
