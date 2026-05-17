import time
import json
from starlette.types import ASGIApp, Scope, Receive, Send, Message
from starlette.datastructures import MutableHeaders
from app.config.logging_config import get_logger

logger = get_logger(__name__)


class LoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        query = scope.get("query_string", b"").decode()
        client = scope.get("client")
        client_host = client[0] if client else None
        request_id = str(int(time.time() * 1000))

        logger.info(
            f"Request started: {method} {path}",
            extra={"extra_data": {
                "request_id": request_id,
                "method": method,
                "path": path,
                "query_params": query,
                "client_host": client_host,
            }},
        )

        start_time = time.time()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                process_time = time.time() - start_time
                headers.append("X-Request-ID", request_id)
                headers.append("X-Process-Time", f"{process_time:.3f}")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            process_time = time.time() - start_time
            logger.info(
                f"Request completed: {method} {path} - Status: {status_code}",
                extra={"extra_data": {
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "process_time": f"{process_time:.3f}s",
                }},
            )
