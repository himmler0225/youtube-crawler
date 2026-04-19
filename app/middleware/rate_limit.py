import os
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
from app.config.logging_config import get_logger

logger = get_logger(__name__)


def get_api_key_from_request(request: Request) -> str:
    api_key = request.headers.get("X-API-Key", "anonymous")

    if api_key and api_key != "anonymous":
        return f"apikey:{api_key[:8]}"

    return get_remote_address(request)


def get_identifier(request: Request) -> str:
    """Use API key prefix as rate limit identifier, fallback to IP."""
    api_key = request.headers.get("X-API-Key", "")
    ip_address = get_remote_address(request)

    if api_key:
        identifier = f"key_{api_key[:8]}"
        logger.debug(f"Rate limit identifier: {identifier}")
        return identifier
    else:
        identifier = f"ip_{ip_address}"
        logger.debug(f"Rate limit identifier: {identifier}")
        return identifier


limiter = Limiter(
    key_func=get_identifier,
    default_limits=[
        os.getenv("RATE_LIMIT_DEFAULT", "100/hour"),
        os.getenv("RATE_LIMIT_BURST", "20/minute"),
    ],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE", "memory://"),  # Use Redis in production
    headers_enabled=True,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    identifier = get_identifier(request)

    logger.warning(
        f"Rate limit exceeded",
        extra={
            "extra_data": {
                "identifier": identifier,
                "path": request.url.path,
                "method": request.method,
                "limit": str(exc.detail),
            }
        }
    )

    return _rate_limit_exceeded_handler(request, exc)
