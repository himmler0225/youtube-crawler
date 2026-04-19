import os
from typing import Set, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.logging_config import get_logger

logger = get_logger(__name__)


def get_whitelisted_ips() -> Set[str]:
    whitelist_env = os.getenv("WHITELISTED_IPS", "")

    if not whitelist_env:
        logger.warning("No IP whitelist configured - all IPs will be allowed")
        return set()

    ips = {ip.strip() for ip in whitelist_env.split(",") if ip.strip()}

    if os.getenv("APP_ENV", "development") == "development":
        ips.update({"127.0.0.1", "::1", "localhost"})

    logger.info(f"Loaded {len(ips)} whitelisted IPs")
    return ips


def get_whitelisted_services() -> Set[str]:
    services_env = os.getenv("WHITELISTED_SERVICES", "")

    if not services_env:
        return set()

    services = {s.strip() for s in services_env.split(",") if s.strip()}
    logger.info(f"Loaded {len(services)} whitelisted services")
    return services


WHITELISTED_IPS = get_whitelisted_ips()
WHITELISTED_SERVICES = get_whitelisted_services()
WHITELIST_ENABLED = os.getenv("ENABLE_IP_WHITELIST", "false").lower() == "true"


def is_ip_whitelisted(ip: str) -> bool:
    if not WHITELISTED_IPS:
        return True  # No whitelist configured, allow all

    return ip in WHITELISTED_IPS


def is_service_whitelisted(service_name: Optional[str]) -> bool:
    if not WHITELISTED_SERVICES:
        return False

    if not service_name:
        return False

    return service_name in WHITELISTED_SERVICES


def get_client_ip(request: Request) -> str:
    """Resolve real client IP, preferring X-Forwarded-For then X-Real-IP."""
    forwarded_for = request.headers.get("X-Forwarded-For")  # format: "client, proxy1, proxy2"
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not WHITELIST_ENABLED:
            return await call_next(request)

        if request.url.path == "/health":
            return await call_next(request)

        client_ip = get_client_ip(request)
        service_name = request.headers.get("X-Service-Name")
        service_token = request.headers.get("X-Service-Token")

        if service_name and service_token:
            expected_token = os.getenv(f"SERVICE_TOKEN_{service_name.upper()}")
            if expected_token and service_token == expected_token:
                if is_service_whitelisted(service_name):
                    logger.debug(f"Request from whitelisted service: {service_name}")
                    return await call_next(request)

        if is_ip_whitelisted(client_ip):
            logger.debug(f"Request from whitelisted IP: {client_ip}")
            return await call_next(request)

        logger.warning(
            f"Blocked request from non-whitelisted source",
            extra={
                "extra_data": {
                    "ip": client_ip,
                    "service": service_name,
                    "path": request.url.path,
                    "method": request.method,
                }
            }
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: IP address or service not whitelisted"
        )
