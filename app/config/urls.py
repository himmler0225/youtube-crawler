import os
from typing import Optional
from app.config.proxy_manager import ProxyManager

YOUTUBE_BASE_URL = os.getenv("YOUTUBE_BASE_URL", "https://www.youtube.com")
YOUTUBE_API_BASE = os.getenv("YOUTUBE_API_BASE", "https://www.youtube.com/youtubei/v1")

# PROXY_KEYS: danh sách key xoay từ proxyxoay.shop, cách nhau bằng dấu phẩy
_raw = os.getenv("PROXY_KEYS", "")
_PROXY_LIST: list = [k.strip() for k in _raw.split(",") if k.strip()]

proxy_manager = ProxyManager(_PROXY_LIST)


def get_proxy() -> Optional[str]:
    """Legacy sync getter — trả None, dùng await proxy_manager.get_proxy() thay thế."""
    return None


def get_youtube_api_url(endpoint: str, api_key: str) -> str:
    return f"{YOUTUBE_API_BASE}/{endpoint}?key={api_key}"
