import os
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.scheduler.scheduler import get_scheduler
from app.scheduler.jobs import (
    crawl_trending_videos,
    crawl_popular_keywords,
    cleanup_old_data,
    health_check_job
)
from app.config.logging_config import get_logger

logger = get_logger(__name__)


def configure_jobs():
    scheduler = get_scheduler()

    enable_scheduler = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"

    if not enable_scheduler:
        logger.info("Scheduler is disabled via ENABLE_SCHEDULER env var")
        return

    trending_schedule = os.getenv("TRENDING_CRON", "0 6 * * *")
    scheduler.add_job(
        crawl_trending_videos,
        trigger=CronTrigger.from_crontab(trending_schedule),
        id="crawl_trending",
        name="Crawl Trending Videos",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Scheduled job: Crawl Trending Videos (cron: {trending_schedule})")

    keywords_schedule = os.getenv("KEYWORDS_CRON", "0 8 * * *")
    scheduler.add_job(
        crawl_popular_keywords,
        trigger=CronTrigger.from_crontab(keywords_schedule),
        id="crawl_keywords",
        name="Crawl Popular Keywords",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Scheduled job: Crawl Popular Keywords (cron: {keywords_schedule})")

    cleanup_schedule = os.getenv("CLEANUP_CRON", "0 2 * * 0")
    scheduler.add_job(
        cleanup_old_data,
        trigger=CronTrigger.from_crontab(cleanup_schedule),
        id="cleanup_data",
        name="Cleanup Old Data",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Scheduled job: Cleanup Old Data (cron: {cleanup_schedule})")

    health_interval_minutes = int(os.getenv("HEALTH_CHECK_INTERVAL", "60"))
    scheduler.add_job(
        health_check_job,
        trigger=IntervalTrigger(minutes=health_interval_minutes),
        id="health_check",
        name="Periodic Health Check",
        replace_existing=True,
        max_instances=1,
    )
    logger.info(f"Scheduled job: Health Check (every {health_interval_minutes} minutes)")

    logger.info(f"Total scheduled jobs: {len(scheduler.get_jobs())}")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        next_run_str = next_run.isoformat() if next_run else "N/A"
        logger.info(f"  - {job.name} (ID: {job.id}, Next run: {next_run_str})")

