import os
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.config.logging_config import get_logger

logger = get_logger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_keys() -> set[str]:
    api_keys_env = os.getenv("API_KEYS", "")

    if not api_keys_env:
        logger.warning("No API_KEYS configured in environment variables")
        return set()

    keys = {key.strip() for key in api_keys_env.split(",") if key.strip()}
    logger.info(f"Loaded {len(keys)} API keys from environment")
    return keys


VALID_API_KEYS = get_api_keys()


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if not VALID_API_KEYS:
        logger.error("API authentication attempted but no API keys configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API authentication not configured"
        )

    if not api_key:
        logger.warning("Request without API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
            headers={"WWW-Authenticate": "APIKey"},
        )

    if api_key not in VALID_API_KEYS:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key"
        )

    logger.debug(f"Valid API key used: {api_key[:8]}...")
    return api_key


def get_optional_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """Returns key if valid, None otherwise."""
    if not api_key:
        return None

    if VALID_API_KEYS and api_key in VALID_API_KEYS:
        return api_key

    return None
