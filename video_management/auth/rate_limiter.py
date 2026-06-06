"""Security utilities for API protection."""

import logging
import time
from typing import Dict, Optional, Any, Callable
from functools import wraps

from fastapi import HTTPException, status, Request

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter for API endpoints."""
    
    def __init__(self):
        self._requests: Dict[str, list] = {}
        self._blocked: Dict[str, float] = {}
    
    def is_allowed(self, key: str, max_requests: int = 5, window: int = 60) -> bool:
        """Check if request is allowed under rate limit.
        
        Args:
            key: Unique identifier (e.g., IP + endpoint)
            max_requests: Maximum requests allowed in window
            window: Time window in seconds
            
        Returns:
            True if request is allowed
        """
        now = time.time()
        
        # Check if currently blocked
        if key in self._blocked:
            if now < self._blocked[key]:
                return False
            del self._blocked[key]
        
        # Clean old requests
        if key in self._requests:
            self._requests[key] = [
                req_time for req_time in self._requests[key]
                if now - req_time < window
            ]
        else:
            self._requests[key] = []
        
        # Check limit
        if len(self._requests[key]) >= max_requests:
            # Block for window duration
            self._blocked[key] = now + window
            logger.warning(f"Rate limit exceeded for {key}")
            return False
        
        self._requests[key].append(now)
        return True


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 5, window: int = 60):
    """Decorator to apply rate limiting to endpoint handlers.
    
    Args:
        max_requests: Maximum requests allowed in window
        window: Time window in seconds
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try to extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request is None:
                request = kwargs.get('request')
            
            if request:
                client_ip = request.client.host if request.client else "unknown"
                key = f"{client_ip}:{func.__name__}"
            else:
                key = f"unknown:{func.__name__}"
            
            if not _rate_limiter.is_allowed(key, max_requests, window):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class SecurityHeadersMiddleware:
    """Middleware to add security headers to all responses."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                
                # Prevent clickjacking
                headers.append([b"x-frame-options", b"DENY"])
                
                # Prevent MIME type sniffing
                headers.append([b"x-content-type-options", b"nosniff"])
                
                # XSS Protection
                headers.append([b"x-xss-protection", b"1; mode=block"])
                
                # Referrer Policy
                headers.append([b"referrer-policy", b"strict-origin-when-cross-origin"])
                
                # Content Security Policy
                headers.append([
                    b"content-security-policy",
                    b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
                ])
                
                # Strict Transport Security (HTTPS only)
                # headers.append([b"strict-transport-security", b"max-age=31536000; includeSubDomains"])
                
                message["headers"] = headers
            
            await send(message)
        
        await self.app(scope, receive, send_with_headers)
