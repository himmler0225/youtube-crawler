import re
import httpx
import json
from .config.urls import YOUTUBE_BASE_URL, get_proxy
from .config.constants import (
    CLIENT_NAME, CLIENT_VERSION, CLIENT_HL, CLIENT_GL, DEFAULT_TIMEOUT
)

async def get_youtube_api_key(proxy: str = None) -> str:
    async with create_httpx_client(proxy=proxy) as client:
        resp = await client.get(YOUTUBE_BASE_URL)
        html = resp.text
        match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
        if not match:
            raise Exception("INNERTUBE_API_KEY not found")
        return match.group(1)

def get_context():
    return {
        "client": {
            "hl": CLIENT_HL,
            "gl": CLIENT_GL,
            "clientName": CLIENT_NAME,
            "clientVersion": CLIENT_VERSION,
        }
    }

async def resolve_channel_id_from_handle(handle: str) -> str:
    async with create_httpx_client() as client:
        url = f"{YOUTUBE_BASE_URL}/@{handle}"
        resp = await client.get(url)
        html = resp.text
        match = re.search(r'channel_id=([a-zA-Z0-9_-]{24})', html)
        if match:
            return match.group(1)

        match = re.search(r'"browseId":"(UC[^\"]+)"', html)
        if match:
            return match.group(1)

        raise Exception("Channel_id not found")

def save_to_json(data, filename="debug.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_default_proxy():
    return get_proxy()

def get_httpx_proxies(proxy: str = None):
    if proxy is None:
        proxy = get_proxy()

    if proxy:
        return proxy

    return None

def create_httpx_client(proxy: str = None, headers: dict = None, timeout: int = DEFAULT_TIMEOUT):
    proxies = get_httpx_proxies(proxy)

    kwargs = {"timeout": timeout}

    if headers:
        kwargs["headers"] = headers

    if proxies:
        kwargs["proxies"] = proxies

    return httpx.AsyncClient(**kwargs)