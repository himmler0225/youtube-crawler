import asyncio
import json
from typing import List, Dict
from ..utils import get_youtube_api_key, get_context, create_httpx_client
from ..config import get_youtube_headers, get_youtube_api_url
from ..config.constants import ENDPOINT_SEARCH, SEARCH_FILTER_LOCATION
from ..exceptions import YouTubeStructureChangedError
from ..config.logging_config import get_logger

logger = get_logger(__name__)

def extract_videos_from_search(items: List[Dict]) -> List[Dict]:
    results = []
    for item in items:
        video = item.get("videoRenderer")
        if not video:
            continue
        results.append({
            "video_id": video.get("videoId"),
            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
            "channel_name": video.get("ownerText", {}).get("runs", [{}])[0].get("text", ""),
            "views": video.get("viewCountText", {}).get("simpleText", ""),
            "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
            "url": f"https://www.youtube.com/watch?v={video.get('videoId')}"
        })
    return results

import math

def generate_grid_locations(center_lat, center_lng, step_km=10, radius_km=50):
    R = 6371
    grid = []

    num_steps = int(radius_km / step_km)
    for dx in range(-num_steps, num_steps + 1):
        for dy in range(-num_steps, num_steps + 1):
            distance = math.sqrt(dx ** 2 + dy ** 2) * step_km
            if distance > radius_km:
                continue

            d_lat = (step_km * dx) / R
            d_lng = (step_km * dy) / (R * math.cos(math.radians(center_lat)))

            lat = center_lat + math.degrees(d_lat)
            lng = center_lng + math.degrees(d_lng)
            grid.append(f"{lat:.6f},{lng:.6f}")

    return grid


async def get_videos_by_location(location: str, proxy: str = None, radius: str = "500km", max_results: int = 50) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    SEARCH_URL = get_youtube_api_url(ENDPOINT_SEARCH, API_KEY)
    headers = get_youtube_headers()

    payload = {
        "context": get_context(),
        "query": "*",
        "params": SEARCH_FILTER_LOCATION,
        "location": location,
        "locationRadius": radius,
        "maxResults": max_results
    }
    
    collected = []
    continuation = None

    async with create_httpx_client(proxy=proxy, headers=headers) as client:
        resp = await client.post(SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Log top-level keys and first 2 levels to inspect current YouTube structure
        logger.debug(
            "YouTube location search raw response (top-level)",
            extra={"extra_data": {
                "location": location,
                "top_keys": list(data.keys()),
                "contents_keys": list(data.get("contents", {}).keys()),
                "raw_preview": json.dumps(data, ensure_ascii=False)[:3000],
            }}
        )

        section_contents = (
            data
            .get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )
        if not section_contents:
            logger.warning(
                "section_contents empty — dumping full response to debug",
                extra={"extra_data": {
                    "location": location,
                    "full_response": json.dumps(data, ensure_ascii=False)[:8000],
                }}
            )
            raise YouTubeStructureChangedError(
                "sectionListRenderer.contents not found in location search response",
                context={"location": location, "top_keys": list(data.get("contents", {}).keys())}
            )
        
        for section in section_contents:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            videos = extract_videos_from_search(items)
            if videos:
                collected += videos

        continuation = None
        for section in section_contents:
            if "itemSectionRenderer" in section:
                continuations = section["itemSectionRenderer"].get("continuations")
                if continuations:
                    continuation = continuations[0].get("continuationItemRenderer", {}) \
                                                  .get("continuationEndpoint", {}) \
                                                  .get("continuationCommand", {}) \
                                                  .get("token")
                    if continuation:
                        break
        
        while continuation and len(collected) < max_results:
            cont_payload = {"context": get_context(), "continuation": continuation}
            resp = await client.post(SEARCH_URL, json=cont_payload)
            resp.raise_for_status()
            data = resp.json()
            
            commands = data.get("onResponseReceivedCommands", [])
            items = (commands[0] if commands else {}) \
                        .get("appendContinuationItemsAction", {}) \
                        .get("continuationItems", [])
            collected += extract_videos_from_search(items)
            
            continuation = next(
                (item.get("continuationItemRenderer", {}) \
                    .get("continuationEndpoint", {}) \
                    .get("continuationCommand", {}) \
                    .get("token")
                 for item in items if "continuationItemRenderer" in item),
                None
            )
    
    return collected[:max_results]

async def get_all_location_videos(center_lat: float, center_lng: float, proxy: str = None, step_km: int = 10, radius_km: int = 50, max_results_per_loc: int = 20):
    locations = generate_grid_locations(center_lat, center_lng, step_km=step_km, radius_km=radius_km)

    tasks = [get_videos_by_location(loc, proxy=proxy, radius="10km", max_results=max_results_per_loc) for loc in locations]
    results = await asyncio.gather(*tasks)

    all_videos = []
    seen = set()
    for videos in results:
        for v in videos:
            vid = v.get("video_id")
            if vid and vid not in seen:
                all_videos.append(v)
                seen.add(vid)

    return all_videos