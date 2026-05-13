import logging
from typing import Optional, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from auth.security import decode_access_token

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

# Default user getter - can be overridden
def get_user_by_username(username: str) -> Optional[Any]:
    """Get user by username.
    
    This is a placeholder that should be overridden by the application
    to integrate with the actual user database/models.
    
    Expected user object should have:
    - username: str
    - hashed_password: str
    - is_active: bool
    """
    # TODO: Import and use actual database models
    # from models import User
    # return database.query(User).filter(User.username == username).first()
    return None


def override_get_user(func):
    """Override the default get_user_by_username function."""
    global get_user_by_username
    get_user_by_username = func
    return func


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> Any:
    """Validate JWT token and return current user.
    
    Args:
        token: JWT bearer token from request.
    
    Returns:
        User object if token is valid.
    
    Raises:
        HTTPException: If token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        logger.warning("Invalid or expired token")
        raise credentials_exception
    
    username: Optional[str] = payload.get("sub")
    if username is None:
        logger.warning("Token missing 'sub' claim")
        raise credentials_exception
    
    user = get_user_by_username(username)
    if user is None:
        logger.warning(f"User '{username}' not found for token")
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: Any = Depends(get_current_user),
) -> Any:
    """Validate that the current user is active.
    
    Args:
        current_user: User object from get_current_user.
    
    Returns:
        User object if active.
    
    Raises:
        HTTPException: If user is inactive.
    """
    if not getattr(current_user, "is_active", True):
        logger.warning(f"Inactive user '{current_user.username}' attempted access")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user
