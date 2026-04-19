import asyncio
import random
import re
import time
import httpx
from typing import Optional
from app.config.logging_config import get_logger

# Nhà mạng hỗ trợ
_NHA_MANG = ["Random", "viettel", "fpt", "vnpt"]

# Tỉnh thành: 0 = Random, các giá trị khác theo danh sách proxyxoay.shop
_TINH_THANH = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

logger = get_logger(__name__)

PROXY_API_URL = "https://proxyxoay.shop/api/get.php"


class ProxyManager:
    """
    Quản lý proxy xoay từ proxyxoay.shop.
    - Rotate qua nhiều key, mỗi key giới hạn 60s/lần gọi API.
    - Cache proxy đến khi hết hạn (TTL từ response).
    """

    def __init__(self, keys: list):
        self._keys = keys
        self._cache: dict = {}      # key -> {proxy_url, expires_at}
        self._last_fetch: dict = {} # key -> timestamp của lần gọi API gần nhất
        self._index = 0
        self._lock = asyncio.Lock()

    async def get_proxy(self) -> Optional[str]:
        if not self._keys:
            return None

        async with self._lock:
            for _ in range(len(self._keys)):
                key = self._keys[self._index % len(self._keys)]
                self._index += 1

                # Dùng cache nếu proxy chưa hết hạn
                cached = self._cache.get(key)
                if cached and time.time() < cached["expires_at"]:
                    return cached["proxy_url"]

                # Giới hạn 60s/lần gọi API mỗi key
                last = self._last_fetch.get(key, 0)
                if time.time() - last < 62:
                    continue

                proxy_url = await self._fetch(key)
                if proxy_url:
                    return proxy_url

        return None

    async def _fetch(self, key: str) -> Optional[str]:
        self._last_fetch[key] = time.time()
        try:
            nha_mang = random.choice(_NHA_MANG)
            tinh_thanh = random.choice(_TINH_THANH)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    PROXY_API_URL,
                    params={"key": key, "nhamang": nha_mang, "tinhthanh": tinh_thanh},
                )
                data = resp.json()

            if data.get("status") != 100:
                logger.warning(f"Proxy API [{key[:8]}]: status={data.get('status')} — {data.get('message')}")
                return None

            # Format: "host:port:user:pass" — user/pass có thể rỗng (dùng IP whitelist)
            raw = data.get("proxyhttp", "")
            parts = raw.split(":")
            if len(parts) < 2:
                logger.warning(f"Proxy API [{key[:8]}]: unexpected format: {raw}")
                return None

            host, port = parts[0], parts[1]
            user = parts[2] if len(parts) > 2 else ""
            password = parts[3] if len(parts) > 3 else ""

            if user and password:
                proxy_url = f"http://{user}:{password}@{host}:{port}"
            else:
                proxy_url = f"http://{host}:{port}"

            # Parse TTL từ message "proxy nay se die sau 1777s"
            ttl = 300
            match = re.search(r"(\d+)s", data.get("message", ""))
            if match:
                ttl = max(int(match.group(1)) - 30, 30)

            self._cache[key] = {"proxy_url": proxy_url, "expires_at": time.time() + ttl}
            logger.info(f"Proxy [{key[:8]}]: {host}:{port} | {nha_mang} / tinh {tinh_thanh} (TTL {ttl}s)")
            return proxy_url

        except Exception as e:
            logger.error(f"Proxy API [{key[:8]}] failed: {e}")
            return None

    def status(self) -> list:
        now = time.time()
        result = []
        for key in self._keys:
            cached = self._cache.get(key)
            result.append({
                "key": key[:8] + "...",
                "cached": bool(cached and now < cached["expires_at"]),
                "expires_in": round(cached["expires_at"] - now) if cached and now < cached["expires_at"] else 0,
                "last_fetch_ago": round(now - self._last_fetch[key]) if key in self._last_fetch else None,
            })
        return result
