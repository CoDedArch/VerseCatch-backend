import hashlib
from typing import Optional

from .config import settings


def hash_key(key: str) -> str:
    """Hash the key using SHA-256."""
    key = key or ""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(api_key: Optional[str] = None) -> bool:
    """
    Verify the API key hashed is the same as the one in the settings.

    Args:
        - api_key (Optional[str]): The API key to verify.
        
    Returns:
        - bool: Whether the API key is valid.
    """
    if hash_key(api_key) == settings.API_KEY:
        return True
    return False
