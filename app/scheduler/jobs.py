# TODO: Connect database to persist crawl results (currently only logging)

import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine
from app.services.trending import get_trending_videos
from app.services.search import search_youtube
from app.exceptions import YouTubeStructureChangedError
from app.config import get_proxy
from app.config.logging_config import get_logger
from app import ingest_client

logger = get_logger(__name__)

PROXY_URL = get_proxy()

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


async def crawl_trending_videos():
    """
    Crawl video trending từ YouTube — chạy hằng ngày lúc 06:00
    Lấy tối đa 100 video thuộc danh mục music (có thể cấu hình thêm)
    """
    job_id = "crawl_trending"

    # Circuit breaker: ngừng chạy nếu đã fail quá nhiều lần liên tiếp
    if _is_circuit_open(job_id):
        logger.critical(
            f"Job '{job_id}' is disabled after {MAX_CONSECUTIVE_FAILURES} "
            "consecutive failures — manual intervention required"
        )
        return {"success": False, "error": "circuit_open"}

    try:
        logger.info("Starting scheduled trending videos crawl...")
        start_time = datetime.now()

        # Retry tối đa 3 lần cho lỗi mạng; không retry nếu cấu trúc thay đổi
        trending = await _with_retry(
            get_trending_videos,
            max_results=100,
            proxy=PROXY_URL,
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Đẩy data vào API — không raise nếu thất bại, sẽ crawl lại lần sau
        await ingest_client.ingest_trending(videos=trending, category="Now")

        _record_success(job_id)
        logger.info(
            "Trending videos crawl completed successfully",
            extra={
                "extra_data": {
                    "videos_count": len(trending),
                    "duration_seconds": duration,
                }
            }
        )

        return {
            "success": True,
            "videos_count": len(trending),
            "duration": duration
        }

    except YouTubeStructureChangedError as e:
        # Cấu trúc YouTube thay đổi — cần fix code, không retry
        count = _record_failure(job_id)
        logger.critical(
            f"YouTube structure changed in trending crawl: {e}",
            extra={"extra_data": {"consecutive_failures": count, "context": e.context}}
        )
        return {"success": False, "error": "structure_changed", "detail": str(e)}

    except Exception as e:
        count = _record_failure(job_id)
        logger.error(
            f"Error during trending videos crawl (failure #{count}): {e}",
            exc_info=True
        )
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
                videos = await _with_retry(
                    search_youtube,
                    query=keyword,
                    max_results=20,
                    sort="upload_date",
                    proxy=PROXY_URL,
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
