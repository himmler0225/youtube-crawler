from typing import List, Dict, Optional
from ..utils import get_youtube_api_key, get_context, create_httpx_client
from ..config import get_youtube_headers, get_youtube_api_url
from ..config.constants import ENDPOINT_BROWSE, BROWSE_ID_TRENDING
from ..exceptions import YouTubeStructureChangedError

def extract_videos(items: List[Dict]) -> List[Dict]:
    results = []
    for item in items:
        video = item.get("videoRenderer") or item.get("gridVideoRenderer")
 
        if not video:
            continue
        results.append({
            "video_id": video.get("videoId"),
            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
            "thumbnail": video.get("thumbnail", {}).get("thumbnails", []),
            "channel_name": video.get("shortBylineText", {}).get("runs", [{}])[0].get("text", ""),
            "views": video.get("shortViewCountText", {}).get("simpleText", ""),
            "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
            "url": f"https://www.youtube.com/watch?v={video.get('videoId')}"
        })
    return results

def extract_videos_from_item(item: Dict) -> List[Dict]:
    if "carouselRenderer" in item:
        return extract_videos(item["carouselRenderer"].get("contents", []))
    elif "shelfRenderer" in item:
        return extract_videos(item["shelfRenderer"]
                              .get("content", {})
                              .get("expandedShelfContentsRenderer", {})
                              .get("items", []))
    elif "richSectionRenderer" in item:
        content = item["richSectionRenderer"].get("content", {})
        if "richShelfRenderer" in content:
            return extract_videos(content["richShelfRenderer"].get("contents", []))
    return []

async def get_trending_videos(
    proxy: Optional[str] = None,
    max_results: int = 100,
    filter_params: Optional[str] = None
) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    BROWSE_URL = get_youtube_api_url(ENDPOINT_BROWSE, API_KEY)
    headers = get_youtube_headers()

    collected: List[Dict] = []
    continuation: Optional[str] = None

    async with create_httpx_client(proxy=proxy, headers=headers) as client:
        payload = {"context": get_context(), "browseId": BROWSE_ID_TRENDING}
        if filter_params:
            payload["params"] = filter_params

        resp = await client.post(BROWSE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Safe navigation — avoid IndexError on empty tabs and KeyError on structure changes
        tabs = (
            data
            .get("contents", {})
            .get("twoColumnBrowseResultsRenderer", {})
            .get("tabs", [])
        )
        if not tabs:
            raise YouTubeStructureChangedError(
                "twoColumnBrowseResultsRenderer.tabs is empty or missing",
                context={"top_keys": list(data.get("contents", {}).keys())}
            )

        renderers = (
            tabs[0]
            .get("tabRenderer", {})
            .get("content", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in renderers:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                collected += extract_videos_from_item(item)
                if len(collected) >= max_results:
                    return collected[:max_results]

            continuation = next(
                (section.get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                 for section in renderers if "continuationItemRenderer" in section),
                None
            )

        while continuation and len(collected) < max_results:
            payload = {"context": get_context(), "continuation": continuation}
            resp = await client.post(BROWSE_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("onResponseReceivedActions", [{}])[0] \
                        .get("appendContinuationItemsAction", {}) \
                        .get("continuationItems", [])

            for item in items:
                if "richItemRenderer" in item:
                    video = item["richItemRenderer"].get("content", {})
                    collected += extract_videos([video])
                elif "itemSectionRenderer" in item:
                    for sub in item["itemSectionRenderer"].get("contents", []):
                        collected += extract_videos_from_item(sub)

                if len(collected) >= max_results:
                    return collected[:max_results]

            continuation = next(
                (item.get("continuationItemRenderer", {})
                      .get("continuationEndpoint", {})
                      .get("continuationCommand", {})
                      .get("token")
                 for item in items if "continuationItemRenderer" in item),
                None
            )

    return collected[:max_results]
