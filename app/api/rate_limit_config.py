RATE_LIMITS = {
    "search": "30/minute",
    "trending": "20/minute",
    "live": "20/minute",
    "video_detail": "60/minute",
    "channel_info": "60/minute",
    "channel_videos": "10/minute",
    "playlist": "10/minute",
    "comments": "15/minute",
    "location": "5/minute",
}

BURST_LIMITS = {
    "search": "10/10seconds",
    "video_detail": "20/10seconds",
    "heavy": "3/10seconds",
}

SERVICE_RATE_LIMITS = {
    "youtube-api": "200/minute",
    "default": "50/minute",
}


def get_rate_limit(endpoint_type: str) -> str:
    return RATE_LIMITS.get(endpoint_type, "30/minute")


def get_service_rate_limit(service_name: str) -> str:
    return SERVICE_RATE_LIMITS.get(service_name, SERVICE_RATE_LIMITS["default"])
