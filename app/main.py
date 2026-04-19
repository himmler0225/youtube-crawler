from dotenv import load_dotenv
load_dotenv()  # Must be called before any import that reads env vars

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from app.api.routes import router as youtube_router
from app.api.admin import router as admin_router
from app.middleware import (
    LoggingMiddleware,
    IPWhitelistMiddleware,
    limiter,
    rate_limit_exceeded_handler
)
from app.config.logging_config import setup_logging, get_logger
from app.scheduler import start_scheduler, shutdown_scheduler, configure_jobs

log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level=log_level)
logger = get_logger(__name__)

app = FastAPI(
    title="YouTube Crawler API",
    description="API for crawling YouTube data with authentication, rate limiting and IP whitelisting",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# TODO: update allowed origins for production
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(IPWhitelistMiddleware)
app.add_middleware(LoggingMiddleware)
app.include_router(youtube_router, prefix="/api", tags=["YouTube"])
app.include_router(admin_router, tags=["Admin"])


@app.on_event("startup")
async def startup_event():
    logger.info("YouTube Crawler API starting up...")
    logger.info(f"Log level: {log_level}")

    whitelist_enabled = os.getenv("ENABLE_IP_WHITELIST", "false")
    logger.info(f"IP Whitelist enabled: {whitelist_enabled}")

    rate_limit_default = os.getenv("RATE_LIMIT_DEFAULT", "100/hour")
    logger.info(f"Rate limit: {rate_limit_default}")

    try:
        configure_jobs()
        start_scheduler()
        logger.info("Scheduler initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {str(e)}", exc_info=True)


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("YouTube Crawler API shutting down...")
    try:
        shutdown_scheduler()
        logger.info("Scheduler stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {str(e)}", exc_info=True)


@app.get("/health", tags=["Health"])
async def health_check():
    """No auth required — for load balancer / uptime monitor."""
    return {
        "status": "healthy",
        "service": "youtube-crawler",
        "version": "1.0.0"
    }
