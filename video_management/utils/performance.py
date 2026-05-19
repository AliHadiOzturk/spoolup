"""Performance optimization utilities."""

import functools
import logging
import time
from typing import Any, Callable, Optional

from sqlalchemy.orm import Query

logger = logging.getLogger(__name__)


def cache_response(timeout_seconds: int = 60):
    """Decorator to cache function results in memory.
    
    Args:
        timeout_seconds: How long to keep the cache
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from arguments
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()
            
            # Check if we have a valid cached result
            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < timeout_seconds:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache[key] = (result, now)
            
            # Clean old entries if cache gets too large
            if len(cache) > 100:
                oldest = min(cache.keys(), key=lambda k: cache[k][1])
                del cache[oldest]
            
            return result
        
        return wrapper
    return decorator


def optimize_query(query: Query) -> Query:
    """Add eager loading to a SQLAlchemy query to avoid N+1 queries.
    
    Args:
        query: SQLAlchemy Query object
        
    Returns:
        Optimized query with eager loading
    """
    from sqlalchemy.orm import selectinload
    from database.models import Video, ProcessedVideo, Upload
    
    # Add selectinload for common relationships based on the model
    if query.column_descriptions[0]["type"] == Video:
        query = query.options(
            selectinload(Video.printer),
            selectinload(Video.processed_videos).selectinload(ProcessedVideo.uploads)
        )
    elif query.column_descriptions[0]["type"] == ProcessedVideo:
        query = query.options(
            selectinload(ProcessedVideo.video),
            selectinload(ProcessedVideo.uploads)
        )
    elif query.column_descriptions[0]["type"] == Upload:
        query = query.options(
            selectinload(Upload.processed_video).selectinload(ProcessedVideo.video)
        )
    
    return query


def paginate_query(query: Query, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
    """Paginate a SQLAlchemy query.
    
    Args:
        query: SQLAlchemy Query object
        page: Page number (1-based)
        per_page: Items per page
        
    Returns:
        Dict with 'items', 'total', 'page', 'per_page', 'pages', 'has_next', 'has_prev'
    """
    total = query.count()
    pages = (total + per_page - 1) // per_page
    
    # Ensure valid page
    page = max(1, min(page, pages)) if pages > 0 else 1
    
    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def measure_time(func: Callable) -> Callable:
    """Decorator to measure and log function execution time.
    
    Args:
        func: Function to measure
        
    Returns:
        Wrapped function
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{func.__name__} took {elapsed:.3f}s")
        return result
    return wrapper
