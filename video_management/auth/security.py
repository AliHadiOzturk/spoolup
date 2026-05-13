import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union

import bcrypt
from jose import JWTError, jwt

from config import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    password_bytes = plain_password.encode("utf-8")
    hash_bytes = hashed_password.encode("utf-8") if isinstance(hashed_password, str) else hashed_password
    return bcrypt.checkpw(password_bytes, hash_bytes)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token.
    
    Args:
        data: Dictionary of claims to encode in the token.
        expires_delta: Optional expiration time override.
    
    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    logger.debug(f"Created access token for user: {data.get('sub', 'unknown')}")
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT access token.
    
    Args:
        token: JWT string to decode.
    
    Returns:
        Decoded payload dictionary or None if invalid.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        return None


def authenticate_user(
    username: str,
    password: str,
    get_user_func,
) -> Optional[Any]:
    """Authenticate a user with username and password.
    
    Args:
        username: Username to authenticate.
        password: Plain text password to verify.
        get_user_func: Callable that returns a user object by username.
    
    Returns:
        User object if authentication succeeds, None otherwise.
    """
    user = get_user_func(username)
    if user is None:
        logger.warning(f"Authentication failed: user '{username}' not found")
        return None
    
    if not verify_password(password, user.password_hash):
        logger.warning(f"Authentication failed: invalid password for '{username}'")
        return None
    
    logger.info(f"User '{username}' authenticated successfully")
    return user
