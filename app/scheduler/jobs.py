import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine
from app.services.location import get_all_location_videos
from app.services.search import search_youtube
from app.exceptions import YouTubeStructureChangedError
from app.config.logging_config import get_logger
from app.config.urls import proxy_manager
from app import ingest_client

logger = get_logger(__name__)

# Circuit breaker: if a job fails MAX_CONSECUTIVE_FAILURES times in a row,
# skip future runs and log CRITICAL to alert the developer.
MAX_CONSECUTIVE_FAILURES = 5
_failure_counts: dict[str, int] = {}


async def _with_retry(
    coro_func: Callable[..., Coroutine],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Retry with linear backoff. Raises immediately on YouTubeStructureChangedError."""
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_func(*args, **kwargs)

        except YouTubeStructureChangedError:
            raise

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
    """Trả về True nếu job đã bị circuit-breaker ngắt (quá nhiều lần fail)."""
    return _failure_counts.get(job_id, 0) >= MAX_CONSECUTIVE_FAILURES


def _record_success(job_id: str) -> None:
    """Reset bộ đếm lỗi sau khi job chạy thành công."""
    _failure_counts[job_id] = 0


def _record_failure(job_id: str) -> int:
    """Tăng bộ đếm lỗi, trả về số lần fail hiện tại."""
    count = _failure_counts.get(job_id, 0) + 1
    _failure_counts[job_id] = count
    return count


# Major cities worldwide — one representative point per country/region
# Each city crawled with radius 50km, step 25km (~9 grid points each)
LOCATION_TARGETS = [
    # Southeast Asia
    {"name": "Hanoi",       "lat": 21.0285,  "lng": 105.8542},
    {"name": "Ho Chi Minh", "lat": 10.8231,  "lng": 106.6297},
    {"name": "Bangkok",     "lat": 13.7563,  "lng": 100.5018},
    {"name": "Jakarta",     "lat": -6.2088,  "lng": 106.8456},
    {"name": "Singapore",   "lat": 1.3521,   "lng": 103.8198},
    {"name": "Manila",      "lat": 14.5995,  "lng": 120.9842},
    {"name": "Kuala Lumpur","lat": 3.1390,   "lng": 101.6869},
    # East Asia
    {"name": "Tokyo",       "lat": 35.6762,  "lng": 139.6503},
    {"name": "Seoul",       "lat": 37.5665,  "lng": 126.9780},
    {"name": "Beijing",     "lat": 39.9042,  "lng": 116.4074},
    {"name": "Shanghai",    "lat": 31.2304,  "lng": 121.4737},
    # South Asia
    {"name": "Mumbai",      "lat": 19.0760,  "lng": 72.8777},
    {"name": "Delhi",       "lat": 28.6139,  "lng": 77.2090},
    # Middle East
    {"name": "Dubai",       "lat": 25.2048,  "lng": 55.2708},
    {"name": "Cairo",       "lat": 30.0444,  "lng": 31.2357},
    # Europe
    {"name": "London",      "lat": 51.5074,  "lng": -0.1278},
    {"name": "Paris",       "lat": 48.8566,  "lng": 2.3522},
    {"name": "Berlin",      "lat": 52.5200,  "lng": 13.4050},
    {"name": "Moscow",      "lat": 55.7558,  "lng": 37.6176},
    # North America
    {"name": "New York",    "lat": 40.7128,  "lng": -74.0060},
    {"name": "Los Angeles", "lat": 34.0522,  "lng": -118.2437},
    {"name": "Toronto",     "lat": 43.6532,  "lng": -79.3832},
    {"name": "Mexico City", "lat": 19.4326,  "lng": -99.1332},
    # South America
    {"name": "Sao Paulo",   "lat": -23.5505, "lng": -46.6333},
    {"name": "Buenos Aires","lat": -34.6037, "lng": -58.3816},
    # Africa
    {"name": "Lagos",       "lat": 6.5244,   "lng": 3.3792},
    {"name": "Johannesburg","lat": -26.2041, "lng": 28.0473},
    # Oceania
    {"name": "Sydney",      "lat": -33.8688, "lng": 151.2093},
]


async def crawl_location_videos():
    """
    Crawl video theo vị trí địa lý — chạy hằng ngày lúc 06:00.
    Duyệt qua danh sách thành phố lớn toàn cầu, mỗi thành phố lấy tối đa 50 video.
    """
    job_id = "crawl_location"

    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    try:
        logger.info(f"Starting location crawl for {len(LOCATION_TARGETS)} cities...")
        start_time = datetime.now()

        total_videos = 0
        skipped = []

        for target in LOCATION_TARGETS:
            city = target["name"]
            try:
                proxy = await proxy_manager.get_proxy()
                videos = await _with_retry(
                    get_all_location_videos,
                    center_lat=target["lat"],
                    center_lng=target["lng"],
                    proxy=proxy,
                    step_km=25,
                    radius_km=50,
                    max_results_per_loc=20,
                )

                if videos:
                    await ingest_client.ingest_trending(videos=videos, category=city)
                    total_videos += len(videos)
                    logger.info(f"[{city}] crawled {len(videos)} videos")

                await asyncio.sleep(3)

            except YouTubeStructureChangedError:
                raise

            except Exception as e:
                logger.warning(f"[{city}] skipped after retries: {e!r}")
                skipped.append(city)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        _record_success(job_id)
        logger.info(
            "Location crawl completed",
            extra={
                "extra_data": {
                    "cities": len(LOCATION_TARGETS),
                    "total_videos": total_videos,
                    "skipped": skipped,
                    "duration_seconds": duration,
                }
            }
        )
        return {
            "success": True,
            "cities": len(LOCATION_TARGETS),
            "total_videos": total_videos,
            "skipped": skipped,
            "duration": duration,
        }

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in location crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}}
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(f"Error during location crawl (failure #{count}): {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def crawl_popular_keywords():
    """
    Crawl video theo danh sách keyword định sẵn — chạy hằng ngày lúc 08:00
    Mỗi keyword lấy 20 video mới nhất, có delay 2s giữa các keyword để tránh bị block.

    Chiến lược xử lý lỗi:
    - YouTubeStructureChangedError: dừng toàn bộ job ngay (cấu trúc đã đổi)
    - Lỗi mạng ở từng keyword: retry rồi skip keyword đó, tiếp tục các keyword còn lại
    """
    job_id = "crawl_keywords"

    # Circuit breaker
    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    # Danh sách keyword cần theo dõi — có thể load từ DB hoặc config file
    keywords = [
        "python tutorial",
        "fastapi",
        "react tutorial",
        "nodejs",
        "machine learning"
    ]

    try:
        logger.info(f"Starting scheduled keyword crawl for {len(keywords)} keywords...")
        start_time = datetime.now()

        results = {}
        skipped = []

        for keyword in keywords:
            try:
                # Retry lỗi mạng; YouTubeStructureChangedError sẽ được bubble up
                proxy = await proxy_manager.get_proxy()
                videos = await _with_retry(
                    search_youtube,
                    query=keyword,
                    max_results=20,
                    sort="upload_date",
                    proxy=proxy,
                )
                results[keyword] = len(videos)
                logger.info(f"Crawled {len(videos)} videos for keyword: '{keyword}'")

                # Đẩy data vào API
                await ingest_client.ingest_search(
                    query=keyword,
                    videos=videos,
                    sort="upload_date",
                )

                # Delay nhỏ giữa các request để tránh bị YouTube rate limit
                await asyncio.sleep(2)

            except YouTubeStructureChangedError:
                # Cấu trúc thay đổi ảnh hưởng tất cả keyword — dừng ngay
                raise

            except Exception as e:
                # Lỗi mạng sau tất cả các lần retry — skip keyword này
                logger.warning(
                    f"Skipping keyword '{keyword}' after all retries: {e!r}"
                )
                results[keyword] = 0
                skipped.append(keyword)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        total_videos = sum(results.values())
        _record_success(job_id)
        logger.info(
            "Keyword crawl completed",
            extra={
                "extra_data": {
                    "keywords_count": len(keywords),
                    "total_videos": total_videos,
                    "skipped": skipped,
                    "duration_seconds": duration,
                    "results": results
                }
            }
        )

        return {
            "success": True,
            "keywords_count": len(keywords),
            "total_videos": total_videos,
            "skipped": skipped,
            "duration": duration
        }

    except YouTubeStructureChangedError as e:
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in keyword crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}}
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(
            f"Error during keyword crawl (failure #{count}): {e}",
            exc_info=True
        )
        return {"success": False, "error": str(e)}


async def cleanup_old_data():
    """
    Dọn dẹp dữ liệu cũ — chạy mỗi Chủ Nhật lúc 02:00
    TODO: Implement logic xóa video > 30 ngày, archive logs cũ, dọn error logs
    """
    try:
        logger.info("Starting scheduled data cleanup...")
        start_time = datetime.now()

        # TODO: Implement database cleanup logic
        # Example:
        # - Delete videos older than 30 days
        # - Archive old crawl logs
        # - Clean up error logs

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"Data cleanup completed",
            extra={
                "extra_data": {
                    "duration_seconds": duration
                }
            }
        )

        return {
            "success": True,
            "duration": duration
        }

    except Exception as e:
        logger.error(f"Error during data cleanup: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def health_check_job():
    """
    Kiểm tra sức khỏe hệ thống định kỳ — chạy mỗi 60 phút
    TODO: Thêm kiểm tra kết nối DB, proxy, API rate limits, disk space
    """
    try:
        logger.debug("Running periodic health check...")

        # TODO: Add actual health checks
        # - Check database connection
        # - Check proxy availability
        # - Check API rate limits
        # - Check disk space

        return {
            "success": True,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }
