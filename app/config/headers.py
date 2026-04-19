import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en;q=0.9",
    "en-US,en;q=0.9,vi;q=0.8",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.8,fr;q=0.7",
]

PLATFORMS = [
    "Windows",
    "macOS",
    "Linux",
]

SCREEN_RESOLUTIONS = [
    (1920, 1080),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (2560, 1440),
    (1600, 900),
    (1280, 720),
    (1920, 1200),
]

DEVICE_MEMORY = [2, 4, 8, 16]
HARDWARE_CONCURRENCY = [2, 4, 6, 8, 12, 16]

def get_youtube_headers() -> dict:
    """
    Returns randomized headers for YouTube API requests to avoid detection
    Includes randomized viewport, screen resolution, device specs
    """
    user_agent = random.choice(USER_AGENTS)
    accept_language = random.choice(ACCEPT_LANGUAGES)
    platform = random.choice(PLATFORMS)
    screen_width, screen_height = random.choice(SCREEN_RESOLUTIONS)

    viewport_width = screen_width - random.randint(0, 20)
    viewport_height = screen_height - random.randint(100, 200)

    device_memory = random.choice(DEVICE_MEMORY)
    hardware_concurrency = random.choice(HARDWARE_CONCURRENCY)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://www.youtube.com",
        "Referer": "https://www.youtube.com/",
        "DNT": str(random.choice([1, 0])),
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Viewport-Width": str(viewport_width),
        "Device-Memory": str(device_memory),
        "X-Youtube-Client-Name": "1",
        "X-Youtube-Client-Version": "2.20240115.00.00",
    }

    if "Chrome" in user_agent and random.random() > 0.3:
        chrome_version = user_agent.split("Chrome/")[1].split(".")[0] if "Chrome/" in user_agent else "120"
        headers["sec-ch-ua"] = f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"'
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = f'"{platform}"'

        if random.random() > 0.5:
            headers["sec-ch-ua-arch"] = f'"{random.choice(["x86", "arm"])}"'
            headers["sec-ch-ua-bitness"] = '"64"'
            headers["sec-ch-ua-model"] = '""'
            headers["sec-ch-ua-platform-version"] = f'"{random.randint(10, 15)}.0.0"'

    return headers
