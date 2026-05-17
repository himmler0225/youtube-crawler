from urllib.parse import unquote
from typing import Any, List, Dict, Optional

from ..utils import get_context, get_youtube_api_key, create_httpx_client, parse_view_count
from ..config import get_youtube_headers, get_youtube_api_url
from ..config.urls import YOUTUBE_BASE_URL
from ..config.constants import ENDPOINT_SEARCH
from ..config.logging_config import get_logger

logger = get_logger(__name__)

_SEEDLESS_PARAMS = "CA8="
_REEL_ENDPOINT   = "reel/reel_item_watch"


# =========================
# UTILS
# =========================
def _extract_text(obj: dict) -> str:
    if not obj:
        return ""
    if "simpleText" in obj:
        return obj.get("simpleText", "")
    runs = obj.get("runs", [])
    if runs:
        return "".join(r.get("text", "") for r in runs)
    return ""


def _next_endpoint(data: dict) -> dict:
    return (
        data.get("replacementEndpoint", {})
            .get("reelWatchEndpoint", {})
    )


def _next_pos_params(data: dict) -> Optional[str]:
    raw = _next_endpoint(data).get("params")
    return unquote(raw) if raw else None


def _shorts_url(video_id: str) -> str:
    return f"{YOUTUBE_BASE_URL}/shorts/{video_id}"


def _parse_short(data: dict) -> Optional[dict]:
    pr = data.get("playerResponse", {})
    details = pr.get("videoDetails", {})
    video_id = details.get("videoId")
    if not video_id:
        return None

    thumbnails = details.get("thumbnail", {}).get("thumbnails", [])
    if not thumbnails:
        thumbnails = [{"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}]

    overlay = data.get("overlay", {}).get("reelPlayerOverlayRenderer", {})

    return {
        "video_id": video_id,
        "title": details.get("title", ""),
        "description": details.get("shortDescription", ""),
        "view_count": parse_view_count(details.get("viewCount", "")),
        "channel_id": details.get("channelId") or None,
        "channel_name": details.get("author", ""),
        "duration": details.get("lengthSeconds"),
        "is_live": details.get("isLiveContent", False),
        "likes": overlay.get("likeButton", {}),
        "comments": overlay.get("commentButton", {}),
        "shares": overlay.get("shareButton", {}),
        "thumbnails": thumbnails,
        "url": _shorts_url(video_id),
        "is_short": True,
        "source": "playerResponse",
    }


def _parse_short_from_replacement(data: dict) -> Optional[dict]:
    ep = _next_endpoint(data)
    video_id = ep.get("videoId")
    if not video_id:
        return None

    thumbnails = ep.get("thumbnail", {}).get("thumbnails", [])
    if not thumbnails:
        thumbnails = [{"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}]

    return {
        "video_id": video_id,
        "title": "",
        "description": "",
        "view_count": 0,
        "channel_id": None,
        "channel_name": "",
        "duration": None,
        "is_live": False,
        "likes": {},
        "comments": {},
        "shares": {},
        "thumbnails": thumbnails,
        "url": _shorts_url(video_id),
        "is_short": True,
        "source": "replacementEndpoint",
    }


# =========================
# SEARCH / BROWSE HELPERS
# =========================
def _find_reel_item_renderers(obj: Any) -> List[tuple]:
    items: List[tuple] = []
    if isinstance(obj, dict):
        if "reelItemRenderer" in obj:
            items.append(("reel", obj["reelItemRenderer"]))
        elif "shortsLockupViewModel" in obj:
            items.append(("lockup", obj["shortsLockupViewModel"]))
        else:
            for v in obj.values():
                items.extend(_find_reel_item_renderers(v))
    elif isinstance(obj, list):
        for item in obj:
            items.extend(_find_reel_item_renderers(item))
    return items


def _parse_reel_item_renderer(item_type: str, item: dict) -> Optional[dict]:
    if item_type == "reel":
        video_id = item.get("videoId")
        if not video_id:
            return None
        title      = _extract_text(item.get("headline", {}))
        views      = _extract_text(item.get("viewCountText", {}))
        byline     = item.get("shortBylineText", {})
        channel    = _extract_text(byline)
        channel_id = (
            byline.get("runs", [{}])[0]
            .get("navigationEndpoint", {})
            .get("browseEndpoint", {})
            .get("browseId")
        ) or None
        thumbnails = item.get("thumbnail", {}).get("thumbnails", [])

    elif item_type == "lockup":
        nav = (
            item.get("onTap", {})
                .get("innertubeCommand", {})
                .get("reelWatchEndpoint", {})
        )
        video_id = nav.get("videoId")
        if not video_id:
            return None
        overlay    = item.get("overlayMetadata", {})
        title      = overlay.get("primaryText", {}).get("content", "")
        views      = overlay.get("secondaryText", {}).get("content", "")
        channel    = ""
        channel_id = None
        thumbnails = item.get("thumbnail", {}).get("image", {}).get("sources", [])

    else:
        return None

    if not thumbnails:
        thumbnails = [{"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}]

    return {
        "video_id": video_id,
        "title": title,
        "description": "",
        "view_count": parse_view_count(views),
        "channel_id": channel_id,
        "channel_name": channel,
        "duration": None,
        "is_live": False,
        "likes": {},
        "comments": {},
        "shares": {},
        "thumbnails": thumbnails,
        "url": _shorts_url(video_id),
        "is_short": True,
        "source": "search",
    }


async def _fetch_shorts_from_search(
    client,
    api_key: str,
    query: str,
    seen_ids: set,
    max_per_query: int = 15,
) -> List[Dict]:
    url = get_youtube_api_url(ENDPOINT_SEARCH, api_key) + "&prettyPrint=false"
    try:
        resp = await client.post(url, json={"context": get_context(), "query": query})
        if not resp.is_success:
            logger.error(f"[shorts:search] '{query}' → HTTP {resp.status_code}")
            return []
        data = resp.json()
    except Exception as e:
        logger.error(f"[shorts:search] '{query}' → {e}")
        return []

    items = _find_reel_item_renderers(data)
    logger.info(f"[shorts:search] '{query}' → {len(items)} items")

    shorts: List[Dict] = []
    for item_type, item in items:
        parsed = _parse_reel_item_renderer(item_type, item)
        if parsed and parsed["video_id"] not in seen_ids:
            seen_ids.add(parsed["video_id"])
            shorts.append(parsed)
            if len(shorts) >= max_per_query:
                break

    return shorts


# =========================
# BOOTSTRAP
# =========================
async def _bootstrap_session(client) -> None:
    for url in (f"{YOUTUBE_BASE_URL}/", f"{YOUTUBE_BASE_URL}/shorts/"):
        try:
            resp = await client.get(url)
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location", "")
                if loc.startswith("/"):
                    loc = f"{YOUTUBE_BASE_URL}{loc}"
                await client.get(loc)
                if "m.youtube.com" in loc:
                    logger.warning("[shorts] redirected to m.youtube.com — WEB context may cycle")
        except Exception as e:
            logger.warning(f"[shorts] bootstrap {url} failed: {e}")


# =========================
# REEL SESSION BATCH
# =========================
async def _fetch_shorts_batch(
    client,
    url: str,
    seen_ids: set,
    batch_limit: int = 8,
) -> List[Dict]:
    batch: List[Dict] = []
    pos_params: Optional[str] = None
    last_pos_params: Optional[str] = None
    tracking_params: Optional[str] = None
    stale_count = 0
    dup_count = 0

    for i in range(batch_limit):
        if i == 0:
            payload: dict = {
                "context": get_context(),
                "params": _SEEDLESS_PARAMS,
                "inputType": "REEL_WATCH_INPUT_TYPE_SEEDLESS",
            }
        else:
            if not pos_params:
                break
            payload = {
                "context": get_context(),
                "params": pos_params,
                "sequenceProvider": "REEL_WATCH_SEQUENCE_PROVIDER_RPC",
                "inputType": "REEL_WATCH_INPUT_TYPE_SEEDLESS",
            }
            if tracking_params:
                payload["clickTrackingParams"] = tracking_params

        try:
            resp = await client.post(url, json=payload)
        except Exception as e:
            logger.error(f"[shorts:reel] step {i} request error: {e}")
            break

        if not resp.is_success:
            logger.error(f"[shorts:reel] step {i} HTTP {resp.status_code}")
            if i == 0:
                resp.raise_for_status()
            break

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"[shorts:reel] step {i} invalid JSON: {e}")
            break

        status = data.get("status", "")
        new_pos = _next_pos_params(data)
        tracking_params = data.get("trackingParams")

        if status != "REEL_ITEM_WATCH_STATUS_SUCCEEDED":
            logger.warning(f"[shorts:reel] step {i} status={status} → end batch")
            break

        parsed = _parse_short(data) or _parse_short_from_replacement(data)
        if parsed:
            vid = parsed["video_id"]
            if vid in seen_ids:
                dup_count += 1
                if dup_count >= 5:
                    logger.debug(f"[shorts:reel] step {i} dup limit → end batch")
                    break
            else:
                dup_count = 0
                seen_ids.add(vid)
                batch.append(parsed)
                logger.info(f"[shorts:reel] +1 → {vid} ({parsed.get('title', '')[:50]})")

        if new_pos and new_pos == last_pos_params:
            stale_count += 1
            if stale_count >= 3:
                logger.debug(f"[shorts:reel] step {i} stale pos_params → end batch")
                break
        else:
            stale_count = 0

        last_pos_params = new_pos
        pos_params = new_pos

        if not pos_params:
            break

    return batch


# =========================
# PUBLIC API
# =========================
async def get_shorts_feed(proxy: str = None, max_results: int = 20) -> List[Dict]:
    api_key = await get_youtube_api_key(proxy=proxy)
    headers = get_youtube_headers()

    async with create_httpx_client(proxy=proxy, headers=headers) as client:
        await _bootstrap_session(client)

        shorts: List[Dict] = []
        seen_ids: set = set()

        # Primary: search → Shorts shelf in results (10-20 items per query)
        for q in ("#shorts", "shorts funny", "shorts viral", "shorts trending 2024"):
            if len(shorts) >= max_results:
                break
            results = await _fetch_shorts_from_search(
                client, api_key, q, seen_ids, max_per_query=max_results,
            )
            shorts.extend(results)
            logger.info(f"[shorts] search '{q}' +{len(results)} → total {len(shorts)}")

        # Fallback: reel_item_watch trending feed
        if len(shorts) < max_results:
            logger.info("[shorts] search insufficient, falling back to reel_item_watch")
            reel_url = get_youtube_api_url(_REEL_ENDPOINT, api_key) + "&prettyPrint=false"
            consecutive_empty = 0
            for restart in range(8):
                if len(shorts) >= max_results:
                    break
                batch = await _fetch_shorts_batch(
                    client, reel_url, seen_ids,
                    batch_limit=max(max_results - len(shorts) + 6, 12),
                )
                if not batch:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    continue
                consecutive_empty = 0
                shorts.extend(batch)
                logger.info(f"[shorts] reel restart={restart} +{len(batch)} → total {len(shorts)}")

    logger.info(f"[shorts] done → {len(shorts)} shorts collected")
    return shorts[:max_results]
