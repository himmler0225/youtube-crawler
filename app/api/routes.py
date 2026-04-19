import asyncio
from fastapi import APIRouter, HTTPException, Query, Depends, Request, Response
from app.services.search import search_youtube
from app.services.detail import get_video_detail
from app.services.channel import get_channel_videos
from app.services.channel_info import get_channel_info
from app.services.playlist import get_playlist_videos, get_videos_from_playlist
from app.services.comment import get_video_comments
from app.services.live import get_all_live_videos
from app.services.trending import get_trending_videos
from app.services.location import generate_grid_locations, get_videos_by_location
from app.utils import resolve_channel_id_from_handle
from app.config import get_proxy
from app.middleware import verify_api_key, limiter
from app.config.logging_config import get_logger

from dotenv import load_dotenv
from functools import wraps
from app.exceptions import YouTubeStructureChangedError

load_dotenv()
router = APIRouter(dependencies=[Depends(verify_api_key)])
logger = get_logger(__name__)

PROXY_URL = get_proxy()

def retry_on_failure(max_retries=3, delay=1):
    """Retry decorator with linear backoff. Raises immediately on YouTubeStructureChangedError."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except YouTubeStructureChangedError as e:
                    logger.critical(
                        f"YouTube structure changed in {func.__name__}: {e}",
                        extra={"extra_data": {"context": e.context}}
                    )
                    raise HTTPException(status_code=502, detail=f"YouTube structure changed: {e}")
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)  # linear backoff
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}. "
                            f"Retrying in {wait_time}s... Error: {str(e)}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    logger.error(f"All {max_retries} attempts failed for {func.__name__}", exc_info=True)
                    raise last_exception
            return None
        return wrapper
    return decorator

@router.get("/search")
@limiter.limit("30/minute")
async def search_videos(
    request: Request,
    response: Response,  # required by slowapi to inject rate-limit headers
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(30, ge=1, le=50, description="Results per page"),
    sort: str = Query("relevance", enum=["relevance", "upload_date", "view_count", "rating"], description="Sort order"),
):
    @retry_on_failure(max_retries=3, delay=1)
    async def _search():
        start = (page - 1) * limit
        max_fetch = start + limit
        results = await search_youtube(q, max_results=max_fetch, sort=sort, proxy=PROXY_URL)
        return {
            "query": q,
            "page": page,
            "limit": limit,
            "total": len(results),
            "results": results[start: start + limit]
        }

    try:
        return await _search()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/video/{video_id}")
async def video_detail(video_id: str):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_detail():
        detail = await get_video_detail(video_id, proxy=PROXY_URL)
        return {"detail": detail}

    try:
        return await _get_detail()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channel/videos")
async def video_channel(
    channel_input: str = Query(..., description="Channel name: @xxx or channel ID: UCxxx"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_channel_videos():
        if channel_input.startswith("@"):
            channel_id = await resolve_channel_id_from_handle(channel_input.lstrip("@"))
        else:
            channel_id = channel_input

        start = (page - 1) * limit
        max_fetch = start + limit
        videos = await get_channel_videos(channel_id=channel_id, max_results=max_fetch, proxy=PROXY_URL)

        return {
            "channel_id": channel_id,
            "video_count": len(videos),
            "videos": videos
        }

    try:
        return await _get_channel_videos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channel/{channel_id}")
async def channel_info(channel_id: str):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_info():
        info = await get_channel_info(channel_id, proxy=PROXY_URL)
        return {"info": info}

    try:
        return await _get_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/channel/{channel_id}/playlist")
async def get_channel_playlists(channel_id: str):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_playlists():
        playlists = await get_playlist_videos(channel_id, proxy=PROXY_URL)
        return {"playlists": playlists}

    try:
        return await _get_playlists()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/playlist/{playlist_id}/videos")
async def get_videos_from_a_playlist(playlist_id: str):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_playlist_videos():
        videos = await get_videos_from_playlist(playlist_id, proxy=PROXY_URL)
        return {"videos": videos}

    try:
        return await _get_playlist_videos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/video/{video_id}/comments")
async def get_comments(
    video_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_comments():
        start = (page - 1) * limit
        max_fetch = start + limit
        comments = await get_video_comments(video_id, proxy=PROXY_URL, max_comments=max_fetch)
        return {
            "video_id": video_id,
            "total": len(comments),
            "comments": comments
        }

    try:
        return await _get_comments()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/videos/live")
async def get_videos_live(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_live():
        start = (page - 1) * limit
        max_fetch = start + limit
        videos = await get_all_live_videos(q=q, proxy=PROXY_URL, max_results=max_fetch)
        return {"videos": videos}

    try:
        return await _get_live()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/videos/trending")
async def get__videos_trending(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=50),
):
    @retry_on_failure(max_retries=3, delay=1)
    async def _get_trending():
        start = (page - 1) * limit
        max_fetch = start + limit
        videos = await get_trending_videos(proxy=PROXY_URL, max_results=max_fetch, filter_params="EgZtdXNpYw%3D%3D")

        return {
            "videos": videos[start:start + limit]
        }

    try:
        return await _get_trending()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/location/videos")
async def get_videos_location(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius_km: int = Query(50, ge=1, le=500, description="Total search radius (km) around location"),
    step_km: int = Query(10, ge=1, le=100, description="Distance between each point in the grid (km)"),
    per_location_limit: int = Query(20, ge=1, le=50, description="Maximum number of videos per coordinate"),
):
    try:
        grid_locations = generate_grid_locations(center_lat=lat, center_lng=lng, step_km=step_km, radius_km=radius_km)

        tasks = [
            get_videos_by_location(location=loc, radius=f"{step_km}km", max_results=per_location_limit)
            for loc in grid_locations
        ]

        results = await asyncio.gather(*tasks)

        # Deduplicate by videoId across grid points
        unique = {}
        for video_list in results:
            for video in video_list:
                unique[video["videoId"]] = video

        return {
            "center": f"{lat},{lng}",
            "locations_scanned": len(grid_locations),
            "total_unique_videos": len(unique),
            "videos": list(unique.values())
        }

    except Exception as e:
        return {"error": str(e)}