import re
import json
import random
from typing import List, Dict, Optional
from ..utils import get_youtube_api_key, get_context, get_httpx_proxies, create_httpx_client, parse_view_count
from ..config import get_youtube_headers, get_youtube_api_url
from ..config.constants import ENDPOINT_BROWSE, ENDPOINT_SEARCH, SORT_VIEW_COUNT, DEFAULT_TIMEOUT
from ..config.headers import USER_AGENTS
from ..exceptions import YouTubeStructureChangedError
from ..config.logging_config import get_logger
import httpx

logger = get_logger(__name__)

TRENDING_URL = "https://www.youtube.com/feed/trending"


def extract_videos(items: List[Dict], rank_offset: int = 0) -> List[Dict]:
    results = []
    for item in items:
        video = item.get("videoRenderer") or item.get("gridVideoRenderer")
        if not video:
            continue

        video_id = video.get("videoId")
        if not video_id:
            continue

        owner_runs = video.get("ownerText", {}).get("runs", [{}])
        channel_id = (
            owner_runs[0]
            .get("navigationEndpoint", {})
            .get("browseEndpoint", {})
            .get("browseId")
        )

        results.append({
            "video_id": video_id,
            "rank": rank_offset + len(results) + 1,
            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
            "thumbnails": video.get("thumbnail", {}).get("thumbnails", []),
            "channel": video.get("shortBylineText", {}).get("runs", [{}])[0].get("text", ""),
            "channel_id": channel_id,
            "view_count": parse_view_count(video.get("shortViewCountText", {}).get("simpleText", "")),
            "duration": video.get("lengthText", {}).get("simpleText", ""),
            "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
        })
    return results


def extract_videos_from_item(item: Dict, rank_offset: int = 0) -> List[Dict]:
    if "carouselRenderer" in item:
        return extract_videos(item["carouselRenderer"].get("contents", []), rank_offset)
    elif "shelfRenderer" in item:
        return extract_videos(
            item["shelfRenderer"]
            .get("content", {})
            .get("expandedShelfContentsRenderer", {})
            .get("items", []),
            rank_offset,
        )
    elif "richSectionRenderer" in item:
        content = item["richSectionRenderer"].get("content", {})
        if "richShelfRenderer" in content:
            return extract_videos(content["richShelfRenderer"].get("contents", []), rank_offset)
    return []


def _parse_yt_initial_data(html: str) -> dict:
    match = re.search(r'var ytInitialData\s*=\s*', html)
    if not match:
        raise YouTubeStructureChangedError(
            "ytInitialData not found in trending page HTML",
            context={"html_length": len(html)},
        )
    try:
        data, _ = json.JSONDecoder().raw_decode(html, match.end())
        return data
    except json.JSONDecodeError as e:
        raise YouTubeStructureChangedError(
            f"Failed to parse ytInitialData: {e}",
            context={"offset": match.end()},
        )


def _make_session(proxy: Optional[str], gl: str, hl: str) -> httpx.AsyncClient:
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": f"{hl}-{gl},{hl};q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    # PREF cookie sets region/language; SOCS bypasses consent gate
    cookies = {
        "PREF": f"tz=Asia%2FHo_Chi_Minh&hl={hl}&gl={gl}",
        "SOCS": "CAESEwgDEgk0ODE5Mzk4MTgaAmVuIAEaBgiA_LyaBg",
    }
    proxies = get_httpx_proxies(proxy)
    kwargs: dict = {
        "headers": headers,
        "cookies": cookies,
        "timeout": DEFAULT_TIMEOUT,
        "follow_redirects": True,
    }
    if proxies:
        kwargs["proxies"] = proxies
    return httpx.AsyncClient(**kwargs)


async def _html_trending(
    proxy: Optional[str],
    max_results: int,
    filter_params: Optional[str],
    gl: str,
    hl: str,
) -> List[Dict]:
    params = f"gl={gl}&hl={hl}"
    if filter_params:
        params += f"&bp={filter_params}"
    page_url = f"{TRENDING_URL}?{params}"

    async with _make_session(proxy=proxy, gl=gl, hl=hl) as client:
        resp = await client.get(page_url)
        resp.raise_for_status()
        data = _parse_yt_initial_data(resp.text)

    contents = data.get("contents", {})
    tabs = (
        contents
        .get("twoColumnBrowseResultsRenderer", {})
        .get("tabs", [])
    )
    if not tabs:
        raise YouTubeStructureChangedError(
            "twoColumnBrowseResultsRenderer.tabs is empty or missing",
            context={"contents_keys": list(contents.keys())},
        )

    first_tab = tabs[0].get("tabRenderer", {})
    tab_content = first_tab.get("content", {})

    if "richGridRenderer" in tab_content:
        renderers = tab_content["richGridRenderer"].get("contents", [])
    else:
        renderers = tab_content.get("sectionListRenderer", {}).get("contents", [])

    collected: List[Dict] = []
    continuation: Optional[str] = None

    for item in renderers:
        if "richItemRenderer" in item:
            video = item["richItemRenderer"].get("content", {})
            collected += extract_videos([video], rank_offset=len(collected))
        elif "richSectionRenderer" in item or "shelfRenderer" in item or "carouselRenderer" in item:
            collected += extract_videos_from_item(item, rank_offset=len(collected))
        elif "continuationItemRenderer" in item:
            continuation = (
                item["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
        if len(collected) >= max_results:
            return collected[:max_results]

    if continuation and len(collected) < max_results:
        api_headers = get_youtube_headers()
        api_key = await get_youtube_api_key(proxy=proxy)
        browse_url = get_youtube_api_url(ENDPOINT_BROWSE, api_key)
        ua = api_headers.get("User-Agent")

        async with create_httpx_client(proxy=proxy, headers=api_headers) as client:
            while continuation and len(collected) < max_results:
                payload = {
                    "context": get_context(original_url=TRENDING_URL, user_agent=ua),
                    "continuation": continuation,
                }
                resp = await client.post(browse_url, json=payload)
                resp.raise_for_status()
                cont_data = resp.json()

                items = (
                    cont_data.get("onResponseReceivedActions", [{}])[0]
                    .get("appendContinuationItemsAction", {})
                    .get("continuationItems", [])
                )

                for item in items:
                    if "richItemRenderer" in item:
                        video = item["richItemRenderer"].get("content", {})
                        collected += extract_videos([video], rank_offset=len(collected))
                    elif "itemSectionRenderer" in item:
                        for sub in item["itemSectionRenderer"].get("contents", []):
                            collected += extract_videos_from_item(sub, rank_offset=len(collected))
                    if len(collected) >= max_results:
                        return collected[:max_results]

                continuation = next(
                    (
                        item.get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                        for item in items
                        if "continuationItemRenderer" in item
                    ),
                    None,
                )

    return collected


async def _search_trending(
    proxy: Optional[str],
    max_results: int,
    gl: str,
    hl: str,
) -> List[Dict]:
    # Datacenter IPs get feedNudgeRenderer instead of trending — search by view count as proxy.
    api_headers = get_youtube_headers()
    api_key = await get_youtube_api_key(proxy=proxy)
    search_url = get_youtube_api_url(ENDPOINT_SEARCH, api_key)

    context = get_context(original_url=TRENDING_URL, user_agent=api_headers.get("User-Agent"))
    context["client"]["hl"] = hl
    context["client"]["gl"] = gl

    payload = {
        "context": context,
        "query": "",
        "params": SORT_VIEW_COUNT,
    }

    collected: List[Dict] = []
    continuation: Optional[str] = None

    async with create_httpx_client(proxy=proxy, headers=api_headers) as client:
        resp = await client.post(search_url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        sections = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        for section in sections:
            if "itemSectionRenderer" in section:
                for item in section["itemSectionRenderer"].get("contents", []):
                    video = item.get("videoRenderer")
                    if not video or not video.get("videoId"):
                        continue
                    owner_runs = video.get("ownerText", {}).get("runs", [{}])
                    channel_id = (
                        owner_runs[0]
                        .get("navigationEndpoint", {})
                        .get("browseEndpoint", {})
                        .get("browseId")
                    )
                    collected.append({
                        "video_id": video.get("videoId"),
                        "rank": len(collected) + 1,
                        "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
                        "thumbnails": video.get("thumbnail", {}).get("thumbnails", []),
                        "channel": owner_runs[0].get("text", ""),
                        "channel_id": channel_id,
                        "view_count": parse_view_count(
                            video.get("viewCountText", {}).get("simpleText", "")
                        ),
                        "duration": video.get("lengthText", {}).get("simpleText", ""),
                        "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
                    })
            if "continuationItemRenderer" in section:
                continuation = (
                    section["continuationItemRenderer"]
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )
            if len(collected) >= max_results:
                return collected[:max_results]

        while continuation and len(collected) < max_results:
            cont_payload = {"context": context, "continuation": continuation}
            resp = await client.post(search_url, json=cont_payload)
            resp.raise_for_status()
            cont_data = resp.json()

            commands = cont_data.get("onResponseReceivedCommands", [])
            items = (
                commands[0]
                .get("appendContinuationItemsAction", {})
                .get("continuationItems", [])
            ) if commands else []

            for section in items:
                if "itemSectionRenderer" in section:
                    for item in section["itemSectionRenderer"].get("contents", []):
                        video = item.get("videoRenderer")
                        if not video or not video.get("videoId"):
                            continue
                        owner_runs = video.get("ownerText", {}).get("runs", [{}])
                        channel_id = (
                            owner_runs[0]
                            .get("navigationEndpoint", {})
                            .get("browseEndpoint", {})
                            .get("browseId")
                        )
                        collected.append({
                            "video_id": video.get("videoId"),
                            "rank": len(collected) + 1,
                            "title": video.get("title", {}).get("runs", [{}])[0].get("text", ""),
                            "thumbnails": video.get("thumbnail", {}).get("thumbnails", []),
                            "channel": owner_runs[0].get("text", ""),
                            "channel_id": channel_id,
                            "view_count": parse_view_count(
                                video.get("viewCountText", {}).get("simpleText", "")
                            ),
                            "duration": video.get("lengthText", {}).get("simpleText", ""),
                            "published_time": video.get("publishedTimeText", {}).get("simpleText", ""),
                        })
                if "continuationItemRenderer" in section:
                    continuation = (
                        section["continuationItemRenderer"]
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )
                if len(collected) >= max_results:
                    return collected[:max_results]

    return collected


async def get_trending_videos(
    proxy: Optional[str] = None,
    max_results: int = 100,
    filter_params: Optional[str] = None,
    gl: str = "VN",
    hl: str = "vi",
) -> List[Dict]:
    logger.info(f"Fetching trending gl={gl}")

    collected: List[Dict] = []
    try:
        collected = await _html_trending(proxy, max_results, filter_params, gl, hl)
    except YouTubeStructureChangedError as e:
        logger.warning(f"Trending HTML structure changed ({e}) — falling back to search-by-view-count")

    if not collected:
        logger.warning("Trending HTML returned no videos — falling back to search-by-view-count")
        collected = await _search_trending(proxy, max_results, gl, hl)

    logger.info(f"Trending crawl done: {len(collected)} videos")
    return collected[:max_results]
