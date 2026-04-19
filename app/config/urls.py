import os

YOUTUBE_BASE_URL = os.getenv("YOUTUBE_BASE_URL", "https://www.youtube.com")
YOUTUBE_API_BASE = os.getenv("YOUTUBE_API_BASE", "https://www.youtube.com/youtubei/v1")

PROXIES = os.getenv("PROXIES")

def get_proxy() -> str:
    return PROXIES

def get_youtube_api_url(endpoint: str, api_key: str) -> str:
    return f"{YOUTUBE_API_BASE}/{endpoint}?key={api_key}"
