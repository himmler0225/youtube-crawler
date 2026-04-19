from typing import List, Dict
from ..utils import get_youtube_api_key, get_context, create_httpx_client
from ..config import get_youtube_api_url
from ..config.constants import ENDPOINT_BROWSE
from ..exceptions import YouTubeStructureChangedError


def extract_playlists_tab_info(data):
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])

    browse_id = None
    params = None

    for tab in tabs:
        tab_renderer = tab.get("tabRenderer", {})
        title = tab_renderer.get("title", "").lower()
        if title == "videos":
            endpoint = tab_renderer.get("endpoint", {}).get("browseEndpoint", {})
            browse_id = endpoint.get("browseId")
            params = endpoint.get("params")
            break

    if not browse_id or not params:
        raise YouTubeStructureChangedError(
            "Cannot find browseId or params for the Videos tab",
            context={"tabs_count": len(tabs)}
        )

    return browse_id, params


async def get_playlist_videos(channel_id: str, proxy: str = None) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    BROWSER_URL = get_youtube_api_url(ENDPOINT_BROWSE, API_KEY)

    async with create_httpx_client(proxy=proxy) as client:
        payload = {"context": get_context()}
        payload["browseId"] = channel_id
        resp = await client.post(BROWSER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        playlists = []

        browse_id, params = extract_playlists_tab_info(data)

        if not browse_id or not params:
            raise YouTubeStructureChangedError(
                "browseId and params not found after first browse request",
                context={"channel_id": channel_id}
            )

        payload = {"context": get_context()}
        payload["browseId"] = browse_id
        payload["params"] = params

        resp = await client.post(BROWSER_URL, json=payload)
        resp.raise_for_status()
        playlist_data = resp.json()

        contents = playlist_data.get("contents", {}) \
                                .get("twoColumnBrowseResultsRenderer", {}) \
                                .get("tabs", [])
                                
        target_tab = None
        for tab in contents:
            tab_renderer = tab.get("tabRenderer", {})
            title = tab_renderer.get("title", "").lower()
            if title == "playlists":
                target_tab = tab_renderer
                break

        if not target_tab or "content" not in target_tab:
            endpoint = (target_tab or {}).get("endpoint", {}).get("browseEndpoint", {})
            browse_id = endpoint.get("browseId")
            params = endpoint.get("params")
            if not browse_id or not params:
                raise YouTubeStructureChangedError(
                    "browseId and params not found for Playlists tab endpoint",
                    context={"channel_id": channel_id}
                )

            payload = {"context": get_context()}
            payload["browseId"] = browse_id
            payload["params"] = params

            resp = await client.post(BROWSER_URL, json=payload)
            resp.raise_for_status()
            playlist_data = resp.json()

            contents = playlist_data.get("contents", {}) \
                                    .get("twoColumnBrowseResultsRenderer", {}) \
                                    .get("tabs", [])
            target_tab = next(
                (tab.get("tabRenderer", {}) for tab in contents
                 if tab.get("tabRenderer", {}).get("title", "").lower() == "playlists"),
                None
            )
            if not target_tab:
                raise YouTubeStructureChangedError(
                    "Playlists tab not found after second browseEndpoint request",
                    context={"channel_id": channel_id}
                )

        contents = target_tab.get("content", {}) \
                             .get("sectionListRenderer", {})

        for section in contents.get("contents", []):
            item_section = section.get("itemSectionRenderer", {})
            for item in item_section.get("contents", []):
                for grid_item in item.get("gridRenderer", {}).get("items", []):
                    lockup = grid_item.get("lockupViewModel", {})
                    thumbnail_url = (
                        lockup.get("contentImage", {})
                              .get("collectionThumbnailViewModel", {})
                              .get("primaryThumbnail", {})
                              .get("thumbnailViewModel", {})
                              .get("image", {})
                              .get("sources", [{}])[-1]
                              .get("url", "")
                    )
                    
                    videoCount = ""
                    
                    overlays = (
                        lockup.get("contentImage", {})
                              .get("collectionThumbnailViewModel", {})
                              .get("primaryThumbnail", {})
                              .get("thumbnailViewModel", {})
                              .get("overlays", [])
                    )

                    for overlay in overlays:
                        badge = overlay.get("thumbnailOverlayBadgeViewModel", {}).get("thumbnailBadges", [])
                        if badge:
                            videoCount = badge[0].get("thumbnailBadgeViewModel", {}).get("text", "")
                            if videoCount:
                                break
                    
                    title = (
                        lockup.get("metadata", {})
                            .get("lockupMetadataViewModel", {})
                            .get("title", {})
                            .get("content", "")
                    )
                        
                    playlist_id = (
                        lockup.get("rendererContext", {})
                            .get("commandContext", {})
                            .get("onTap", {})
                            .get("innertubeCommand", {})
                            .get("watchEndpoint", {})
                            .get("playlistId", "")
                    )

                    playlists.append({
                        "playlistId": playlist_id,
                        "title": title,
                        "thumbnail": thumbnail_url,
                        "videoCount": videoCount
                    })

        return playlists

def extract_title(title_obj):
    if "simpleText" in title_obj:
        return title_obj["simpleText"]
    elif "runs" in title_obj and title_obj["runs"]:
        return "".join([run.get("text", "") for run in title_obj["runs"]])
    return ""

async def get_videos_from_playlist(playlist_id: str, proxy: str = None) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    BROWSER_URL = get_youtube_api_url(ENDPOINT_BROWSE, API_KEY)

    payload = {"context": get_context()}
    payload["browseId"] = f"VL{playlist_id}"

    videos = []

    async with create_httpx_client(proxy=proxy) as client:
        while True:
            resp = await client.post(BROWSER_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

            if "contents" not in data:
                raise YouTubeStructureChangedError(
                    "Top-level 'contents' missing in playlist response",
                    context={"playlist_id": playlist_id, "top_keys": list(data.keys())}
                )

            tabs = (
                data
                .get("contents", {})
                .get("twoColumnBrowseResultsRenderer", {})
                .get("tabs", [])
            )
            contents = (
                (tabs[0] if tabs else {})
                .get("tabRenderer", {})
                .get("content", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            playlist_items_list = (
                (contents[0] if contents else {})
                .get("itemSectionRenderer", {})
                .get("contents", [])
            )
            contents = (
                (playlist_items_list[0] if playlist_items_list else {})
                .get("playlistVideoListRenderer", {})
                .get("contents", [])
            )
            if not contents:
                break

            continuation_token = None

            for item in contents:
                if "playlistVideoRenderer" in item:
                    renderer = item["playlistVideoRenderer"]
                    videos.append({
                        "video_id": renderer.get("videoId"),
                        "title": extract_title(renderer.get("title", {})),
                        "published_time": renderer.get("publishedTimeText", {}).get("simpleText", ""),
                        "duration": renderer.get("lengthText", {}).get("simpleText", ""),
                        "thumbnail": renderer.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url", "")
                    })
                elif "continuationItemRenderer" in item:
                    continuation_token = (
                        item
                        .get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )

            if continuation_token:
                payload = {"context": get_context()}
                payload["continuation"] = continuation_token
            else:
                break

    return videos
