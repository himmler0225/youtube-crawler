# HTTP errors are caught and logged but never raised — crawl continues even if ingest fails.
import os
import httpx
from typing import Dict, List, Optional
from app.config.logging_config import get_logger
from app.types import ChannelInfo, SearchVideo, Comment

logger = get_logger(__name__)

INGEST_API_URL = os.getenv("INGEST_API_URL", "http://localhost:3000")
INGEST_SERVICE_KEY = os.getenv("INGEST_SERVICE_KEY", "")

_HEADERS = {
    "X-Service-Key": INGEST_SERVICE_KEY,
    "Content-Type": "application/json",
}


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=INGEST_API_URL, headers=_HEADERS, timeout=30)


def _safe_int(value) -> Optional[int]:
    """Parse int from possibly comma-formatted strings like '1,234,567'."""
    if value is None:
        return None
    cleaned = "".join(c for c in str(value) if c.isdigit())
    return int(cleaned) if cleaned else None


async def ingest_channel(data: ChannelInfo) -> bool:
    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/channel", json=data)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ingest_channel failed: {e!r}")
            return False


async def ingest_search(
    query: str,
    videos: List[SearchVideo],
    sort: str = "relevance",
) -> bool:
    valid_videos = [v for v in videos if v.get("video_id")]
    if not valid_videos:
        return True
    payload = {"query": query, "sort": sort, "videos": valid_videos}

    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/search", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ingest_search failed (query='{query}'): {e!r}")
            return False


async def ingest_detail(
    video_id: str,
    detail: dict,
) -> bool:
    # detail has two shapes: error=True with reason, or full video fields.
    if detail.get("error"):
        payload = {
            "video_id": video_id,
            "error": True,
            "reason": detail.get("reason"),
        }
    else:
        payload = {
            "video_id": video_id,
            "title": detail.get("title"),
            "author": detail.get("author"),
            "views": _safe_int(detail.get("views")),
            "length_seconds": _safe_int(detail.get("length_seconds")),
            "is_live_content": detail.get("is_live_content", False),
        }

    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/detail", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ingest_detail failed (video_id={video_id}): {e!r}")
            return False


async def ingest_trending(
    videos: List[Dict],
    category: Optional[str] = None,
) -> bool:
    valid_videos = [v for v in videos if v.get("video_id")]
    if not valid_videos:
        return True
    payload: Dict = {"videos": valid_videos}
    if category:
        payload["category"] = category

    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/trending", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ingest_trending failed (category={category!r}): {e!r}")
            return False


async def ingest_shorts(videos: List[Dict]) -> bool:
    normalized = []
    for v in videos:
        video_id = v.get("video_id")
        if not video_id:
            continue
        raw_dur = v.get("duration")
        try:
            duration = int(raw_dur) if raw_dur is not None and raw_dur != "" else None
        except (ValueError, TypeError):
            duration = None
        normalized.append({
            "video_id": video_id,
            "title": v.get("title") or None,
            "channel_name": v.get("channel_name") or None,
            "view_count": v.get("view_count") or None,
            "duration": duration,
            "thumbnails": v.get("thumbnails") or None,
        })

    if not normalized:
        return True

    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/shorts", json={"videos": normalized})
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"ingest_shorts failed: {e!r}")
            return False


async def ingest_comments(
    video_id: str,
    comments: List[Comment],
) -> bool:
    payload = {"video_id": video_id, "comments": comments}

    async with _make_client() as client:
        try:
            resp = await client.post("/internal/ingest/comments", json=payload)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(
                f"ingest_comments failed (video_id={video_id}, "
                f"count={len(comments)}): {e!r}"
            )
            return False
