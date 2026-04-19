import base64
from typing import List, Dict
from ..utils import get_youtube_api_key, get_context, create_httpx_client
from ..config import get_youtube_headers, get_youtube_api_url
from ..config.constants import ENDPOINT_BROWSE, CHANNEL_TAB_VIDEOS
from ..exceptions import YouTubeStructureChangedError

def extract_video_items(items: List[Dict]) -> List[Dict]:
    videos = []
    for item in items:
        content = item.get("richItemRenderer", {}).get("content", {}) or item
        video = content.get("videoRenderer") or content.get("gridVideoRenderer")
        if not video:
            continue
        videos.append({
            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
            "videoId": video.get("videoId"),
            "url": f"https://www.youtube.com/watch?v={video.get('videoId')}",
            "duration": video.get("lengthText", {}).get("simpleText", ""),
            "views": video.get("viewCountText", {}).get("simpleText", ""),
            "thumbnail": video.get("thumbnail", {}).get("thumbnails", []),
            "public": video.get("publishedTimeText", {}).get("simpleText", ""),
        })
    return videos

async def get_channel_videos(channel_id: str, proxy: str = None, max_results: int = 100) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    BROWSE_URL = get_youtube_api_url(ENDPOINT_BROWSE, API_KEY)
    headers = get_youtube_headers()

    collected = []
    continuation = None

    encoded = CHANNEL_TAB_VIDEOS
    missing_padding = len(encoded) % 4
    if missing_padding:
        encoded += "=" * (4 - missing_padding)

    decoded = base64.b64decode(encoded).decode("utf-8")

    async with create_httpx_client(proxy=proxy, headers=headers) as client:
        payload = {"context": get_context(), "browseId": channel_id, "params": decoded}
        resp = await client.post(BROWSE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        if not tabs:
            raise YouTubeStructureChangedError(
                "twoColumnBrowseResultsRenderer.tabs not found for channel",
                context={"channel_id": channel_id}
            )

        videos_tab = next((tab for tab in tabs if tab.get("tabRenderer", {}).get("title", "").lower() == "videos"), None)
        
        if videos_tab:
            endpoint = videos_tab.get("tabRenderer", {}).get("endpoint", {}).get("browseEndpoint", {})
            browse_id = endpoint.get("browseId")
            params = endpoint.get("params")

            payload = {"context": get_context(), "browseId": browse_id, "params": params}
            resp = await client.post(BROWSE_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            videos_tab = next((tab for tab in tabs if tab.get("tabRenderer", {}).get("title", "").lower() == "videos"), None)


        if not videos_tab:
            videos_tab = next((tab for tab in tabs if tab.get("tabRenderer", {}).get("title", "").lower() == "home"), None)
            if not videos_tab:
                raise YouTubeStructureChangedError(
                    "Neither 'Videos' nor 'Home' tab found for channel",
                    context={"channel_id": channel_id}
                )

        section = videos_tab.get("tabRenderer", {}).get("content", {}) \
                            .get("richGridRenderer", {}) \
                            .get("contents", [])

        collected += extract_video_items(section)
        continuation = next((
            c.get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {}).get("token")
            for c in section if "continuationItemRenderer" in c
        ), None)
    
        while continuation and len(collected) < max_results:
            payload = {"context": get_context(), "continuation": continuation}
            resp = await client.post(BROWSE_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            commands = data.get("onResponseReceivedCommands") or data.get("onResponseReceivedActions") or []
            if not commands:
                break

            continuation_items = commands[0].get("appendContinuationItemsAction", {}).get("continuationItems", [])
            new_videos = extract_video_items(continuation_items)
            collected += new_videos

            continuation = next((
                i.get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {}).get("token")
                for i in continuation_items if "continuationItemRenderer" in i
            ), None)


    return collected[:max_results]