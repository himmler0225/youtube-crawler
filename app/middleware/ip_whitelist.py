import json
import os
from typing import Set, Optional
from starlette.types import ASGIApp, Scope, Receive, Send
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
        return True

    return ip in WHITELISTED_IPS


def is_service_whitelisted(service_name: Optional[str]) -> bool:
    if not WHITELISTED_SERVICES or not service_name:
        return False

    return service_name in WHITELISTED_SERVICES


def _get_client_ip_from_scope(scope: Scope, headers: dict) -> str:
    forwarded_for = headers.get(b"x-forwarded-for", b"").decode()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = headers.get(b"x-real-ip", b"").decode()
    if real_ip:
        return real_ip.strip()

    client = scope.get("client")
    if client:
        return client[0]

    return "unknown"


async def _send_403(send: Send) -> None:
    body = json.dumps({"detail": "Access denied: IP address or service not whitelisted"}).encode()
    await send({
        "type": "http.response.start",
        "status": 403,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body)).encode()],
        ],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})


class IPWhitelistMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not WHITELIST_ENABLED:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/health":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        client_ip = _get_client_ip_from_scope(scope, headers)
        service_name = headers.get(b"x-service-name", b"").decode() or None
        service_token = headers.get(b"x-service-token", b"").decode() or None

        if service_name and service_token:
            expected_token = os.getenv(f"SERVICE_TOKEN_{service_name.upper()}")
            if expected_token and service_token == expected_token and is_service_whitelisted(service_name):
                logger.debug(f"Request from whitelisted service: {service_name}")
                await self.app(scope, receive, send)
                return

        if is_ip_whitelisted(client_ip):
            logger.debug(f"Request from whitelisted IP: {client_ip}")
            await self.app(scope, receive, send)
            return

        logger.warning(
            "Blocked request from non-whitelisted source",
            extra={
                "extra_data": {
                    "ip": client_ip,
                    "service": service_name,
                    "path": path,
                    "method": scope.get("method", ""),
                }
            },
        )

        await _send_403(send)
