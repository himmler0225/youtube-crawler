import asyncio
from typing import Optional, Set

from .channel_info import get_channel_info
from .channel import get_channel_videos
from .playlist import get_playlist_videos
from .. import ingest_client
from ..config.logging_config import get_logger

logger = get_logger(__name__)

# Max channels enriched concurrently — each channel fires 3 parallel HTTP calls.
_CHANNEL_CONCURRENCY = 2


async def _enrich_one(channel_id: str, proxy: Optional[str] = None) -> None:
    async def _info() -> None:
        try:
            data = await get_channel_info(channel_id, proxy=proxy)
            if data.get("channel_id"):
                await ingest_client.ingest_channel(data)
        except Exception as e:
            logger.warning(f"[enricher] info {channel_id}: {e!r}")

    async def _videos() -> None:
        try:
            videos = await get_channel_videos(channel_id, proxy=proxy, max_results=30)
            if videos:
                await ingest_client.ingest_channel_videos(channel_id=channel_id, videos=videos)
        except Exception as e:
            logger.warning(f"[enricher] videos {channel_id}: {e!r}")

    async def _playlists() -> None:
        try:
            playlists = await get_playlist_videos(channel_id, proxy=proxy)
            if playlists:
                await ingest_client.ingest_playlists(channel_id=channel_id, playlists=playlists)
        except Exception as e:
            logger.warning(f"[enricher] playlists {channel_id}: {e!r}")

    logger.info(f"[enricher] start {channel_id}")
    await asyncio.gather(_info(), _videos(), _playlists())
    logger.info(f"[enricher] done  {channel_id}")


async def enrich_channels_batch(
    channel_ids: Set[str],
    proxy: Optional[str] = None,
    concurrency: int = _CHANNEL_CONCURRENCY,
) -> None:
    if not channel_ids:
        return

    sem = asyncio.Semaphore(concurrency)

    async def _guarded(cid: str) -> None:
        async with sem:
            await _enrich_one(cid, proxy=proxy)

    await asyncio.gather(*[_guarded(cid) for cid in channel_ids], return_exceptions=True)
    logger.info(f"[enricher] batch complete — {len(channel_ids)} channels")
