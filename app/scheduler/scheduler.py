import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.config.logging_config import get_logger

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started successfully")
    else:
        logger.warning("Scheduler already running")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=True)  # wait=True: let running job finish
        logger.info("Scheduler shut down successfully")
    else:
        logger.warning("Scheduler not running")


def get_scheduler() -> AsyncIOScheduler:
    return scheduler
