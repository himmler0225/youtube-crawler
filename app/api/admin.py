import asyncio
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from app.middleware import verify_api_key
from app.utils import get_youtube_api_key, get_context, create_httpx_client
from app.config import get_youtube_headers, get_youtube_api_url
from app.config.constants import ENDPOINT_SEARCH, SEARCH_FILTER_LOCATION
from app.scheduler.jobs import (
    crawl_location_videos,
    crawl_popular_keywords,
    cleanup_old_data,
    health_check_job,
)
from app.config.urls import proxy_manager
from app.config.logging_config import get_logger

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_api_key)])
logger = get_logger(__name__)

_running_jobs: set[str] = set()


async def _run_job(job_id: str, coro):
    if job_id in _running_jobs:
        return {"status": "already_running", "job": job_id}

    _running_jobs.add(job_id)
    try:
        result = await coro()
        return {"status": "done", "job": job_id, "result": result}
    except Exception as e:
        logger.error(f"Manual job {job_id} failed: {e}", exc_info=True)
        return {"status": "error", "job": job_id, "error": str(e)}
    finally:
        _running_jobs.discard(job_id)


@router.get("/proxy/debug")
async def proxy_debug():
    """Raw test: gọi thẳng proxyxoay.shop API với key đầu tiên, trả về response gốc."""
    import os, httpx
    keys_raw = os.getenv("PROXY_KEYS", "")
    keys = [k.strip() for k in keys_raw.split(",") if k.strip()]
    if not keys:
        return {"error": "PROXY_KEYS trống trong .env", "keys_raw": keys_raw}

    key = keys[0]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://proxyxoay.shop/api/get.php",
                params={"key": key, "nhamang": "Random", "tinhthanh": "0"},
            )
            return {"key": key[:8] + "...", "status_code": resp.status_code, "body": resp.text}
    except Exception as e:
        return {"error": repr(e)}


@router.get("/debug/location")
async def debug_location(lat: float = 10.8231, lng: float = 106.6297):
    """Gọi YouTube search API với location và trả về raw response để debug cấu trúc."""
    proxy = await proxy_manager.get_proxy()
    try:
        api_key = await get_youtube_api_key(proxy=proxy)
        search_url = get_youtube_api_url(ENDPOINT_SEARCH, api_key)
        headers = get_youtube_headers()
        payload = {
            "context": get_context(),
            "query": "*",
            "params": SEARCH_FILTER_LOCATION,
            "location": f"{lat},{lng}",
            "locationRadius": "50km",
        }
        async with create_httpx_client(proxy=proxy, headers=headers) as client:
            resp = await client.post(search_url, json=payload)
            data = resp.json()

        # Trả về top-level keys + 3000 ký tự đầu để không bị timeout
        import json
        return {
            "status_code": resp.status_code,
            "top_keys": list(data.keys()),
            "contents_keys": list(data.get("contents", {}).keys()),
            "raw_preview": json.dumps(data, ensure_ascii=False)[:5000],
        }
    except Exception as e:
        return {"error": repr(e)}


@router.get("/proxy/status")
async def proxy_status():
    """Xem trạng thái cache của từng proxy key."""
    return {"proxies": proxy_manager.status()}


@router.get("/proxy/test")
async def test_proxy():
    """Lấy 1 proxy từ API rồi test qua httpbin.org/ip."""
    proxy_url = await proxy_manager.get_proxy()
    if not proxy_url:
        return {"status": "error", "detail": "Không lấy được proxy — kiểm tra PROXY_KEYS trong .env"}

    try:
        async with httpx.AsyncClient(proxies=proxy_url, timeout=10) as client:
            resp = await client.get("http://httpbin.org/ip")
            ip = resp.json().get("origin", "unknown")
        return {"status": "ok", "exit_ip": ip, "proxy": proxy_url}
    except Exception as e:
        return {"status": "error", "proxy": proxy_url, "error": repr(e)}


@router.get("/jobs")
async def list_jobs():
    """Danh sách jobs và trạng thái hiện tại."""
    from app.scheduler.scheduler import get_scheduler
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "running": job.id in _running_jobs,
        })
    return {"jobs": jobs, "running": list(_running_jobs)}


@router.post("/jobs/location")
async def trigger_location(background_tasks: BackgroundTasks):
    """Trigger crawl location videos ngay lập tức (chạy background, duyệt 28 thành phố toàn cầu)."""
    if "crawl_location" in _running_jobs:
        return {"status": "already_running", "job": "crawl_location"}

    async def _run():
        await _run_job("crawl_location", crawl_location_videos)

    background_tasks.add_task(_run)
    return {"status": "started", "job": "crawl_location"}


@router.post("/jobs/keywords")
async def trigger_keywords(background_tasks: BackgroundTasks):
    """Trigger crawl popular keywords ngay lập tức (chạy background)."""
    if "crawl_keywords" in _running_jobs:
        return {"status": "already_running", "job": "crawl_keywords"}

    async def _run():
        await _run_job("crawl_keywords", crawl_popular_keywords)

    background_tasks.add_task(_run)
    return {"status": "started", "job": "crawl_keywords"}


@router.post("/jobs/cleanup")
async def trigger_cleanup(background_tasks: BackgroundTasks):
    """Trigger cleanup ngay lập tức."""
    background_tasks.add_task(cleanup_old_data)
    return {"status": "started", "job": "cleanup_data"}


@router.post("/jobs/health")
async def trigger_health():
    """Chạy health check ngay, trả về kết quả."""
    result = await health_check_job()
    return {"status": "done", "result": result}
