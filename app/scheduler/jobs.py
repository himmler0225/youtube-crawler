import asyncio
import random
from datetime import datetime
from typing import Any, Callable, Coroutine
from app.services.location import get_videos_by_region
from app.services.search import search_youtube
from app.services.trending import get_trending_videos
from app.services.shorts import get_shorts_feed
from app.services.channel_enricher import enrich_channels_batch
from app.exceptions import YouTubeStructureChangedError
from app.config.logging_config import get_logger
from app.config.urls import proxy_manager
from app import ingest_client

logger = get_logger(__name__)

# Circuit breaker: job is disabled after this many consecutive failures.
MAX_CONSECUTIVE_FAILURES = 5
_failure_counts: dict[str, int] = {}

# Max concurrent YouTube requests per batch job.
BATCH_CONCURRENCY = 3


async def _with_retry(
    coro_func: Callable[..., Coroutine],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    **kwargs: Any,
) -> Any:
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_func(*args, **kwargs)
        except YouTubeStructureChangedError:
            raise  # structure errors won't resolve with retries
        except Exception as e:
            if attempt == max_attempts:
                raise
            wait = base_delay * attempt
            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed for {coro_func.__name__}: "
                f"{e!r} — retrying in {wait}s"
            )
            await asyncio.sleep(wait)


def _is_circuit_open(job_id: str) -> bool:
    return _failure_counts.get(job_id, 0) >= MAX_CONSECUTIVE_FAILURES


def _record_success(job_id: str) -> None:
    _failure_counts[job_id] = 0


def _record_failure(job_id: str) -> int:
    count = _failure_counts.get(job_id, 0) + 1
    _failure_counts[job_id] = count
    return count


# gl (country code) drives regional targeting — YouTube ignores lat/lng.
LOCATION_TARGETS = [
    # Southeast Asia
    {"name": "Hanoi",        "gl": "VN", "hl": "vi", "query": "Hà Nội"},
    {"name": "Ho Chi Minh",  "gl": "VN", "hl": "vi", "query": "Sài Gòn"},
    {"name": "Bangkok",      "gl": "TH", "hl": "th", "query": "กรุงเทพ"},
    {"name": "Jakarta",      "gl": "ID", "hl": "id", "query": "Jakarta"},
    {"name": "Singapore",    "gl": "SG", "hl": "en", "query": "Singapore"},
    {"name": "Manila",       "gl": "PH", "hl": "en", "query": "Manila"},
    {"name": "Kuala Lumpur", "gl": "MY", "hl": "ms", "query": "Kuala Lumpur"},
    # East Asia
    {"name": "Tokyo",        "gl": "JP", "hl": "ja", "query": "東京"},
    {"name": "Seoul",        "gl": "KR", "hl": "ko", "query": "서울"},
    {"name": "Shanghai",     "gl": "CN", "hl": "zh-Hans", "query": "上海"},
    # South Asia
    {"name": "Mumbai",       "gl": "IN", "hl": "hi", "query": "Mumbai"},
    # Middle East
    {"name": "Dubai",        "gl": "AE", "hl": "ar", "query": "دبي"},
    {"name": "Cairo",        "gl": "EG", "hl": "ar", "query": "القاهرة"},
    # Europe
    {"name": "London",       "gl": "GB", "hl": "en", "query": "London"},
    {"name": "Paris",        "gl": "FR", "hl": "fr", "query": "Paris"},
    {"name": "Berlin",       "gl": "DE", "hl": "de", "query": "Berlin"},
    {"name": "Moscow",       "gl": "RU", "hl": "ru", "query": "Москва"},
    # North America
    {"name": "New York",     "gl": "US", "hl": "en", "query": "New York"},
    {"name": "Los Angeles",  "gl": "US", "hl": "en", "query": "Los Angeles"},
    {"name": "Toronto",      "gl": "CA", "hl": "en", "query": "Toronto"},
    {"name": "Mexico City",  "gl": "MX", "hl": "es", "query": "Ciudad de México"},
    # South America
    {"name": "Sao Paulo",    "gl": "BR", "hl": "pt", "query": "São Paulo"},
    {"name": "Buenos Aires", "gl": "AR", "hl": "es", "query": "Buenos Aires"},
    # Africa
    {"name": "Lagos",        "gl": "NG", "hl": "en", "query": "Lagos"},
    {"name": "Johannesburg", "gl": "ZA", "hl": "en", "query": "Johannesburg"},
    # Oceania
    {"name": "Sydney",       "gl": "AU", "hl": "en", "query": "Sydney"},
]


async def crawl_trending_videos():
    job_id = "crawl_trending"

    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    try:
        logger.info("Starting trending crawl...")
        start_time = datetime.now()

        proxy = await proxy_manager.get_proxy()
        videos = await _with_retry(get_trending_videos, proxy=proxy, max_results=100, skip_live=True)

        if videos:
            await ingest_client.ingest_trending(videos=videos)

        duration = (datetime.now() - start_time).total_seconds()
        _record_success(job_id)
        logger.info(
            "Trending crawl completed",
            extra={"extra_data": {"total_videos": len(videos), "duration_seconds": duration}},
        )
        return {"success": True, "total_videos": len(videos), "duration": duration}

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in trending crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}},
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(f"Error during trending crawl (failure #{count}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def crawl_shorts_videos():
    job_id = "crawl_shorts"

    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    try:
        logger.info("Starting shorts crawl...")
        start_time = datetime.now()

        proxy = await proxy_manager.get_proxy()
        videos = await _with_retry(get_shorts_feed, proxy=proxy, max_results=50)

        if videos:
            await ingest_client.ingest_shorts(videos=videos)

            channel_ids = {v["channel_id"] for v in videos if v.get("channel_id")}
            if channel_ids:
                logger.info(f"[shorts] enriching {len(channel_ids)} channels in parallel")
                await enrich_channels_batch(channel_ids, proxy=proxy)

        duration = (datetime.now() - start_time).total_seconds()
        _record_success(job_id)
        logger.info(
            "Shorts crawl completed",
            extra={"extra_data": {"total_videos": len(videos), "duration_seconds": duration}},
        )
        return {"success": True, "total_videos": len(videos), "duration": duration}

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in shorts crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}},
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(f"Error during shorts crawl (failure #{count}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def crawl_location_videos():
    job_id = "crawl_location"

    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    try:
        logger.info(f"Starting location crawl for {len(LOCATION_TARGETS)} cities (concurrency={BATCH_CONCURRENCY})...")
        start_time = datetime.now()

        sem = asyncio.Semaphore(BATCH_CONCURRENCY)
        total_videos = 0
        skipped = []

        async def _crawl_city(target: dict) -> int:
            city = target["name"]
            async with sem:
                await asyncio.sleep(random.uniform(0, 1.5))  # stagger to avoid burst
                proxy = await proxy_manager.get_proxy()
                videos = await _with_retry(
                    get_videos_by_region,
                    gl=target["gl"],
                    hl=target["hl"],
                    query=target["query"],
                    proxy=proxy,
                    max_results=50,
                )
                if videos:
                    search_videos = [{k: v for k, v in video.items() if k != "url"} for video in videos]
                    await ingest_client.ingest_search(
                        query=f"location:{city}",
                        videos=search_videos,
                        sort="relevance",
                    )
                    logger.info(f"[{city}] crawled {len(videos)} videos")
                    return len(videos)
                return 0

        tasks = [_crawl_city(t) for t in LOCATION_TARGETS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for target, result in zip(LOCATION_TARGETS, results):
            if isinstance(result, YouTubeStructureChangedError):
                raise result
            elif isinstance(result, Exception):
                logger.warning(f"[{target['name']}] skipped: {result!r}")
                skipped.append(target["name"])
            else:
                total_videos += result

        duration = (datetime.now() - start_time).total_seconds()
        _record_success(job_id)
        logger.info(
            "Location crawl completed",
            extra={"extra_data": {"cities": len(LOCATION_TARGETS), "total_videos": total_videos, "skipped": skipped, "duration_seconds": duration}},
        )
        return {"success": True, "cities": len(LOCATION_TARGETS), "total_videos": total_videos, "skipped": skipped, "duration": duration}

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in location crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}},
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(f"Error during location crawl (failure #{count}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def crawl_popular_keywords():
    job_id = "crawl_keywords"

    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    keywords = [
        "python tutorial",
        "fastapi",
        "react tutorial",
        "nodejs",
        "machine learning",
    ]

    try:
        logger.info(f"Starting keyword crawl for {len(keywords)} keywords (concurrency={BATCH_CONCURRENCY})...")
        start_time = datetime.now()

        sem = asyncio.Semaphore(BATCH_CONCURRENCY)
        skipped = []

        async def _crawl_keyword(keyword: str) -> int:
            async with sem:
                await asyncio.sleep(random.uniform(0, 1.0))
                proxy = await proxy_manager.get_proxy()
                videos = await _with_retry(
                    search_youtube,
                    query=keyword,
                    max_results=20,
                    sort="upload_date",
                    proxy=proxy,
                )
                await ingest_client.ingest_search(query=keyword, videos=videos, sort="upload_date")
                logger.info(f"Crawled {len(videos)} videos for '{keyword}'")
                return len(videos)

        tasks = [_crawl_keyword(kw) for kw in keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        counts: dict[str, int] = {}
        for keyword, result in zip(keywords, results):
            if isinstance(result, YouTubeStructureChangedError):
                raise result
            elif isinstance(result, Exception):
                logger.warning(f"Skipping '{keyword}' after retries: {result!r}")
                skipped.append(keyword)
                counts[keyword] = 0
            else:
                counts[keyword] = result

        total_videos = sum(counts.values())
        duration = (datetime.now() - start_time).total_seconds()
        _record_success(job_id)
        logger.info(
            "Keyword crawl completed",
            extra={"extra_data": {"keywords_count": len(keywords), "total_videos": total_videos, "skipped": skipped, "duration_seconds": duration}},
        )
        return {"success": True, "keywords_count": len(keywords), "total_videos": total_videos, "skipped": skipped, "duration": duration}

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in keyword crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}},
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(f"Error during keyword crawl (failure #{count}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def cleanup_old_data():
    try:
        logger.info("Starting scheduled data cleanup...")
        start_time = datetime.now()
        duration = (datetime.now() - start_time).total_seconds()
        logger.info("Data cleanup completed", extra={"extra_data": {"duration_seconds": duration}})
        return {"success": True, "duration": duration}
    except Exception as e:
        logger.error(f"Error during data cleanup: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def health_check_job():
    try:
        logger.debug("Running periodic health check...")
        return {"success": True, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}
