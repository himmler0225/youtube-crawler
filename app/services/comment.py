from typing import List, Dict
from ..utils import get_youtube_api_key, get_context, create_httpx_client, parse_view_count
from ..config import get_youtube_api_url
from ..config.constants import ENDPOINT_NEXT
from ..exceptions import YouTubeStructureChangedError
from ..config.logging_config import get_logger

logger = get_logger(__name__)


async def fetch_replies(client, continuation_token: str, context: dict, proxy: str = None, max_depth: int = 2) -> List[Dict]:
    replies = []
    API_KEY = await get_youtube_api_key(proxy=proxy)
    URL_COMMENT = get_youtube_api_url(ENDPOINT_NEXT, API_KEY)
    depth = 0

    while continuation_token and depth < max_depth:
        payload = {
            "context": context,
            "continuation": continuation_token
        }

        resp = await client.post(URL_COMMENT, json=payload)
        resp.raise_for_status()
        data = resp.json()

        entity_map = parse_comment_entities(data)
        continuation_token = None
        depth += 1

        actions = data.get("onResponseReceivedEndpoints", [])
        for action in actions:
            items = action.get("appendContinuationItemsAction", {}).get("continuationItems", [])
            for item in items:
                if "commentViewModel" in item:
                    comment_vm = item.get("commentViewModel", {})
                    comment_id = comment_vm.get("commentId")
                    entity = entity_map.get(comment_id, {})

                    if not entity:
                        logger.debug(f"Missing entity for reply commentId={comment_id}")
                        continue

                    replies.append({
                        "comment_id": comment_id,
                        "author": entity.get("author", ""),
                        "avatar": entity.get("avatar"),
                        "content": entity.get("content", ""),
                        "published_time": entity.get("published_time", ""),
                        "likes": entity.get("likes", 0)
                    })

                elif "continuationItemRenderer" in item:
                    continuation_token = (
                        item
                        .get("continuationItemRenderer", {})
                        .get("button", {})
                        .get("buttonRenderer", {})
                        .get("command", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )

    return replies


def extract_comment_continuation_token(data: dict) -> str:
    # Path 1: onResponseReceivedEndpoints — check cả reload lẫn append action
    try:
        for ep in data.get("onResponseReceivedEndpoints", []):
            for action_key in ("reloadContinuationItemsCommand", "appendContinuationItemsAction"):
                items = ep.get(action_key, {}).get("continuationItems", [])
                for item in items:
                    token = (
                        item
                        .get("continuationItemRenderer", {})
                        .get("continuationEndpoint", {})
                        .get("continuationCommand", {})
                        .get("token")
                    )
                    if token:
                        return token
    except Exception as e:
        logger.debug(f"Path 1 (onResponseReceivedEndpoints) failed: {e}")

    # Path 2: twoColumnWatchNextResults
    try:
        results = (
            data
            .get("contents", {})
            .get("twoColumnWatchNextResults", {})
            .get("results", {})
            .get("results", {})
            .get("contents", [])
        )
        for item in results:
            for content in item.get("itemSectionRenderer", {}).get("contents", []):
                token = (
                    content
                    .get("continuationItemRenderer", {})
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )
                if token:
                    return token
    except Exception as e:
        logger.debug(f"Path 2 (twoColumnWatchNextResults) failed: {e}")

    # Path 3: engagementPanels — comment section
    try:
        for panel in data.get("engagementPanels", []):
            renderer = panel.get("engagementPanelSectionListRenderer", {})
            if "comment" not in renderer.get("panelIdentifier", "").lower():
                continue
            section = renderer.get("content", {}).get("sectionListRenderer", {})
            for cont in section.get("continuations", []):
                token = cont.get("nextContinuationData", {}).get("continuation")
                if token:
                    return token
    except Exception as e:
        logger.debug(f"Path 3 (engagementPanels) failed: {e}")

    # Path 4: frameworkUpdates mutations — newer YouTube responses
    try:
        mutations = (
            data
            .get("frameworkUpdates", {})
            .get("entityBatchUpdate", {})
            .get("mutations", [])
        )
        for m in mutations:
            token = (
                m.get("payload", {})
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                return token
    except Exception as e:
        logger.debug(f"Path 4 (frameworkUpdates) failed: {e}")

    return None


def parse_comment_entities(data: dict) -> Dict[str, Dict]:
    result = {}
    mutations = (
        data
        .get("frameworkUpdates", {})
        .get("entityBatchUpdate", {})
        .get("mutations", [])
    )
    for m in mutations:
        payload = m.get("payload", {})
        comment = payload.get("commentEntityPayload", {})
        props = comment.get("properties", {})
        comment_id = props.get("commentId")
        raw_content = props.get("content", {}).get("content", "")
        if not isinstance(raw_content, str):
            continue
        if comment_id:
            result[comment_id] = {
                "content": raw_content,
                "author": comment.get("author", {}).get("displayName", ""),
                "avatar": comment.get("author", {}).get("avatarThumbnailUrl", ""),
                "published_time": props.get("publishedTime", "Unknown"),
                "likes": parse_view_count(comment.get("toolbar", {}).get("likeCountLiked")),
                "replies": parse_view_count(comment.get("toolbar", {}).get("replyCount"))
            }

    return result


async def get_video_comments(video_id: str, proxy: str = None, max_comments: int = 100) -> List[Dict]:
    API_KEY = await get_youtube_api_key(proxy=proxy)
    URL_NEXT = get_youtube_api_url(ENDPOINT_NEXT, API_KEY)
    URL_COMMENT = URL_NEXT
    context = get_context()

    comments = []

    async with create_httpx_client(proxy=proxy) as client:
        payload = {
            "context": context,
            "videoId": video_id
        }
        resp = await client.post(URL_NEXT, json=payload)
        resp.raise_for_status()
        data = resp.json()

        continuation_token = extract_comment_continuation_token(data)
        if not continuation_token:
            raise YouTubeStructureChangedError(
                "No comment continuation token found — structure may have changed",
                context={"video_id": video_id, "top_keys": list(data.keys())}
            )

        while continuation_token and len(comments) < max_comments:
            payload = {
                "context": context,
                "continuation": continuation_token
            }
            resp = await client.post(URL_COMMENT, json=payload)
            resp.raise_for_status()
            data = resp.json()

            entity_map = parse_comment_entities(data)

            continuation_token = None
            actions = data.get("onResponseReceivedEndpoints", [])

            for action in actions:
                items = (
                    action.get("reloadContinuationItemsCommand", {}).get("continuationItems", []) or
                    action.get("appendContinuationItemsAction", {}).get("continuationItems", [])
                )
                for item in items:
                    if "commentThreadRenderer" in item:
                        thread = item["commentThreadRenderer"]

                        comment_vm = thread.get("commentViewModel", {}).get("commentViewModel", {})
                        comment_id = comment_vm.get("commentId")
                        entity = entity_map.get(comment_id, {})
                        if not entity:
                            continue

                        content = entity.get("content", "")
                        if not isinstance(content, str):
                            continue

                        comment_data = {
                            "comment_id": comment_id,
                            "author": entity.get("author", ""),
                            "avatar": entity.get("avatar"),
                            "content": content,
                            "published_time": entity.get("published_time", ""),
                            "likes": entity.get("likes", 0),
                            "replies_count": entity.get("replies", 0),
                            "replies": [],
                        }

                        reply_token = None
                        replies_data = thread.get("replies", {}).get("commentRepliesRenderer", {})
                        for c in replies_data.get("contents", []):
                            continuation = (
                                c
                                .get("continuationItemRenderer", {})
                                .get("continuationEndpoint", {})
                                .get("continuationCommand", {})
                                .get("token")
                            )
                            if continuation:
                                reply_token = continuation
                                break

                        if reply_token:
                            logger.debug(f"Fetching replies for comment {comment_id}")
                            comment_data["replies"] = await fetch_replies(client, reply_token, context, proxy=proxy)

                        comments.append(comment_data)
                        if len(comments) >= max_comments:
                            break

                    elif "continuationItemRenderer" in item:
                        continuation_token = (
                            item
                            .get("continuationItemRenderer", {})
                            .get("continuationEndpoint", {})
                            .get("continuationCommand", {})
                            .get("token")
                        )

                if len(comments) >= max_comments:
                    break

    return comments[:max_comments]
