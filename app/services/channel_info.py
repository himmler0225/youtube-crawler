from typing import Dict
from ..utils import get_youtube_api_key, create_httpx_client
from ..config import get_youtube_api_url

def parse_channel_info(data):
    header = data.get("header", {}).get("pageHeaderRenderer", {})
    metadata = data.get("metadata", {}).get("channelMetadataRenderer", {})

    avatar = None
    try:
        avatar_sources = metadata.get("avatar", {}).get("thumbnails", [])
        avatar = avatar_sources[-1]["url"] if avatar_sources else None
    except Exception:
        pass

    banner = None
    try:
        banner_sources = data.get("header", {}).get("pageHeaderRenderer", {}) \
            .get("banner", {}).get("imageBannerViewModel", {}) \
            .get("image", {}).get("sources", [])
        banner = banner_sources[-1]["url"] if banner_sources else None
    except Exception:
        pass

    handle = None
    subscribers = None
    try:
        metadata_rows = header["content"]["pageHeaderViewModel"]["metadata"]["contentMetadataViewModel"]["metadataRows"]
        for row in metadata_rows:
            for part in row.get("metadataParts", []):
                text = part.get("text", {}).get("content", "")
                if text.startswith("@"):
                    handle = text
                elif "subscribers" in text:
                    subscribers = text
    except Exception:
        pass

    return {
        "channel_id": metadata.get("externalId"),
        "channel_name": metadata.get("title"),
        "handle": handle,
        "avatar": avatar,
        "banner": banner,
        "subscriber_count": subscribers,
        "description": metadata.get("description", "")
    }

async def get_channel_info(channel_id: str, proxy: str = None) -> Dict:
    API_KEY = await get_youtube_api_key()
    BROWSER_URL = get_youtube_api_url("browse", API_KEY)

    payload = {
        "context": {
            "client": {
                "hl": "en",
                "gl": "US",
                "clientName": "WEB",
                "clientVersion": "2.20230401.01.00"
            }
        },
        "browseId": channel_id
    }

    async with create_httpx_client(proxy=proxy) as client:
        resp = await client.post(BROWSER_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        
        return parse_channel_info(data=data)