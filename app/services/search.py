from typing import List, Dict
from ..utils import get_youtube_api_key, get_context, create_httpx_client
from ..config import get_youtube_headers, get_youtube_api_url
from ..exceptions import YouTubeStructureChangedError

SORT_OPTIONS = {
    "relevance": None,
    "upload_date": "CAISAhAB",
    "view_count": "CAMSAhAB",
    "rating": "CAESAhAB",
}

def extract_video_items(items: List[Dict]) -> List[Dict]:
    videos = []

    for item in items:
        content = None

        if "richItemRenderer" in item:
            content = item["richItemRenderer"].get("content", {})
        elif "videoRenderer" in item:
            content = item

        if not content or ("videoRenderer" not in content and "videoId" not in content):
            continue

        video = content.get("videoRenderer") or content

        videos.append({
            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
            "video_id": video.get("videoId"),
            "url": f"https://www.youtube.com/watch?v={video.get('videoId')}",
            "duration": video.get("lengthText", {}).get("simpleText", ""),
            "views": video.get("viewCountText", {}).get("simpleText", ""),
            "channel": video.get("ownerText", {}).get("runs", [{}])[0].get("text", ""),
            "channel_id": video.get("ownerText", {}).get("runs", [{}])[0]
                .get("navigationEndpoint", {})
                .get("browseEndpoint", {})
                .get("browseId", ""),
            "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
            "description_snippet": video.get("detailedMetadataSnippets", [{}])[0]
                .get("snippetText", {}).get("runs", [{}])[0].get("text", ""),
            "thumbnails": video.get("thumbnail", {}).get("thumbnails", [])
        })

    return videos


async def search_youtube(query: str, max_results: int = 50, proxy: str = None, sort: str = "relevance") -> List[Dict]:
    API_KEY = await get_youtube_api_key()
    SEARCH_URL = get_youtube_api_url("search", API_KEY)
    headers = get_youtube_headers()

    collected = []
    continuation = None
    sort_param = SORT_OPTIONS.get(sort)

    async with create_httpx_client(proxy=proxy, headers=headers) as client:
        payload = {
            "context": get_context(),
            "query": query
        }
        
        if sort_param:
            payload["params"] = sort_param

        resp = await client.post(SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Safe navigation to avoid KeyError if YouTube changes response structure
        sections = (
            data
            .get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents")
        )
        if not sections:
            raise YouTubeStructureChangedError(
                "sectionListRenderer.contents not found in search response",
                context={"top_keys": list(data.get("contents", {}).keys())}
            )

        for section in sections:
            if "itemSectionRenderer" in section:
                items = section["itemSectionRenderer"].get("contents", [])
                collected += extract_video_items(items)
            if "continuationItemRenderer" in section:
                continuation = (
                    section.get("continuationItemRenderer", {})
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )

        while continuation and len(collected) < max_results:
            payload = {
                "context": get_context(),
                "continuation": continuation
            }

            resp = await client.post(SEARCH_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            commands = data.get("onResponseReceivedCommands", [])
            continuation_items = (
                commands[0]
                .get("appendContinuationItemsAction", {})
                .get("continuationItems", [])
            ) if commands else []

            for section in continuation_items:
                if "itemSectionRenderer" in section:
                    items = section["itemSectionRenderer"].get("contents", [])
                    collected += extract_video_items(items)
                if "continuationItemRenderer" in section:
                    continuation = (
                        section.get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )

    return collected[:max_results]