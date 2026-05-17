# api

FastAPI routers for public crawler endpoints and admin controls.

## Files

| File | Role |
|------|------|
| `routes.py` | Public `GET /api/*` endpoints; requires `X-API-Key` |
| `admin.py` | Admin `GET|POST /admin/*` endpoints; requires `X-API-Key` |
| `rate_limit_config.py` | Rate limit constants used by `slowapi` |

---

## routes.py — Public API

All routes are mounted under `/api` and protected by `Depends(verify_api_key)`.

### `retry_on_failure` decorator

Applied to every handler's inner async function. 3 attempts, linear backoff (1 s × attempt number).

- `YouTubeStructureChangedError` → raises `HTTP 502` immediately (no retry).
- Any other exception → retries up to 3 times, then re-raises.

### Endpoints

| Method | Path | Query params | Notes |
|--------|------|--------------|-------|
| `GET` | `/api/videos/trending` | `limit` (1–200, default 50) | Calls `get_trending_videos` |
| `GET` | `/api/videos/search` | `q`, `page`, `limit` (1–50), `sort` (relevance/upload_date/view_count/rating) | Rate-limited to 30/minute via `@limiter.limit` |
| `GET` | `/api/videos/shorts` | `limit` (1–50, default 30) | Calls `get_shorts_feed` |
| `GET` | `/api/videos/live` | `q`, `page`, `limit` (1–50, default 30) | Calls `get_all_live_videos` |
| `GET` | `/api/videos/location` | `gl` (country code), `hl` (language, default "en"), `query`, `max_results` (1–100, default 50) | Calls `get_videos_by_region`; no retry decorator (bare try/except) |
| `GET` | `/api/video/{video_id}` | — | Calls `get_video_detail` |
| `GET` | `/api/video/{video_id}/comments` | `page`, `limit` (1–100, default 30) | Calls `get_video_comments` |
| `GET` | `/api/channel/{channel_id}` | — | Calls `get_channel_info` |
| `GET` | `/api/channel/{channel_id}/videos` | `page`, `limit` (1–50, default 30) | Resolves `@handle` via `resolve_channel_id_from_handle` before calling `get_channel_videos` |
| `GET` | `/api/channel/{channel_id}/playlists` | — | Calls `get_playlist_videos` |
| `GET` | `/api/playlist/{playlist_id}/videos` | — | Calls `get_videos_from_playlist` |

Pagination for search, live, comments, and channel videos is offset-based: fetches `(page-1)*limit + limit` items from the service, then slices.

---

## admin.py — Admin API

All routes are mounted under `/admin` and protected by `Depends(verify_api_key)`.

`_running_jobs: set[str]` prevents double-triggering the same job. All job triggers use FastAPI `BackgroundTasks` so the HTTP response returns immediately with `{"status": "started"}`.

### Job endpoints

| Method | Path | Behavior |
|--------|------|---------|
| `GET` | `/admin/jobs` | Lists all APScheduler jobs with `id`, `name`, `next_run` (ISO), `running` (bool). Also returns the current `_running_jobs` set. |
| `POST` | `/admin/jobs/trending` | Triggers `crawl_trending_videos` in background |
| `POST` | `/admin/jobs/shorts` | Triggers `crawl_shorts_videos` in background |
| `POST` | `/admin/jobs/location` | Triggers `crawl_location_videos` in background |
| `POST` | `/admin/jobs/keywords` | Triggers `crawl_popular_keywords` in background |
| `POST` | `/admin/jobs/cleanup` | Triggers `cleanup_old_data` in background (no double-run guard) |
| `POST` | `/admin/jobs/health` | Runs `health_check_job` synchronously, returns result inline |

### Proxy / debug endpoints

| Method | Path | Behavior |
|--------|------|---------|
| `GET` | `/admin/proxy/debug` | Calls proxyxoay.shop API directly with the first `PROXY_KEYS` entry and returns raw response |
| `GET` | `/admin/proxy/status` | Returns `proxy_manager.status()` — cache state of each proxy key |
| `GET` | `/admin/proxy/test` | Fetches a proxy then tests it via `httpbin.org/ip`, returns exit IP |
| `GET` | `/admin/debug/location` | Posts a raw InnerTube search with `location`/`locationRadius` params and returns the top-level response keys + 5000-char preview (for debugging YouTube's lat/lng handling) |

---

## rate_limit_config.py

Defines rate limit strings consumed by `slowapi`. Not automatically applied — each route must call `@limiter.limit(get_rate_limit("search"))` explicitly.

```python
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

SERVICE_RATE_LIMITS = {
    "youtube-api": "200/minute",
    "default": "50/minute",
}
```

Only `/api/videos/search` currently uses `@limiter.limit` directly in `routes.py`. Other endpoints rely on the global default limits set in `rate_limit.py` (`RATE_LIMIT_DEFAULT`, `RATE_LIMIT_BURST` env vars).
