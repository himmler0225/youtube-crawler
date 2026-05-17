# youtube-crawler

FastAPI service that scrapes YouTube via the internal InnerTube API and pushes data to `youtube-api` for storage.

---

## Architecture

```
APScheduler (cron jobs)
  ├── crawl_trending_videos   → POST /internal/ingest/trending
  ├── crawl_shorts_videos     → POST /internal/ingest/shorts
  ├── crawl_location_videos   → POST /internal/ingest/search  (26 cities)
  └── crawl_popular_keywords  → POST /internal/ingest/search

youtube-api (real-time requests)
  ├── GET /api/video/:id               → services/detail.py
  ├── GET /api/video/:id/comments      → services/comment.py
  ├── GET /api/videos/shorts           → services/shorts.py
  └── GET /api/videos/live             → services/live.py
```

---

## Project structure

```
app/
├── api/
│   ├── routes.py              # Public FastAPI endpoints (X-API-Key required)
│   └── admin.py               # Admin endpoints: manual job triggers, proxy debug
├── config/
│   ├── urls.py                # Base URLs + proxy manager
│   ├── headers.py             # Randomised User-Agent, viewport headers
│   ├── constants.py           # InnerTube endpoint names, filter params, sort codes
│   └── logging_config.py      # JSON logger — console, app.log, error.log
├── middleware/
│   ├── auth.py                # verify_api_key FastAPI Depends
│   ├── ip_whitelist.py        # IP whitelist + service token bypass
│   ├── rate_limit.py          # slowapi limiter
│   └── logging_middleware.py  # Request/response logging, X-Request-ID header
├── services/
│   ├── trending.py            # HTML scrape + search-by-view-count fallback
│   ├── shorts.py              # Shorts feed
│   ├── search.py              # Keyword search with continuation
│   ├── live.py                # Live stream search
│   ├── detail.py              # Single video detail
│   ├── comment.py             # Comments + replies
│   ├── channel.py             # Channel videos
│   ├── channel_info.py        # Channel metadata
│   ├── playlist.py            # Playlist videos
│   └── location.py            # Region-targeted search via gl/hl
├── scheduler/
│   ├── scheduler.py           # APScheduler singleton
│   ├── config.py              # Job registration (cron triggers, env overrides)
│   └── jobs.py                # Job implementations (retry, circuit breaker, batch)
├── ingest_client.py           # HTTP client → POST /internal/ingest/*
├── exceptions.py              # YouTubeStructureChangedError, CrawlNetworkError
├── types.py                   # TypedDicts for all data shapes
└── utils.py                   # httpx client factory, proxy helpers, parse_view_count
```

See `README.md` inside each subdirectory for flow details.

---

## API Endpoints

All endpoints require `X-API-Key` header.

| Method | Path | Params | Description |
|--------|------|--------|-------------|
| GET | `/api/videos/search` | `q`, `page`, `limit`, `sort` | Search videos |
| GET | `/api/videos/trending` | `limit` | Trending videos |
| GET | `/api/videos/live` | `q`, `page`, `limit` | Live streams by keyword |
| GET | `/api/videos/shorts` | `limit` | Shorts feed |
| GET | `/api/videos/location` | `gl`, `hl`, `query`, `max_results` | Region-targeted videos |
| GET | `/api/video/{video_id}` | — | Video detail |
| GET | `/api/video/{video_id}/comments` | `page`, `limit` | Comments + replies |
| GET | `/api/channel/{channel_id}` | — | Channel metadata |
| GET | `/api/channel/{channel_id}/videos` | `page`, `limit` | Channel videos |
| GET | `/api/channel/{channel_id}/playlists` | — | Channel playlists |
| GET | `/api/playlist/{playlist_id}/videos` | — | Playlist videos |

> Geographic targeting uses the `gl` country code in the InnerTube request context, not lat/lng (YouTube ignores lat/lng).

---

## Scheduled Jobs

| Job | Default cron | Output |
|-----|-------------|--------|
| `crawl_trending_videos` | `0 7 * * *` | Top 100 trending → `ingest/trending` |
| `crawl_shorts_videos` | `0 9 * * *` | Shorts feed → `ingest/shorts` |
| `crawl_location_videos` | `0 6 * * *` | 26 cities (gl/hl) → `ingest/search` |
| `crawl_popular_keywords` | `0 8 * * *` | Fixed keyword list → `ingest/search` |
| `cleanup_old_data` | `0 2 * * 0` | Weekly cleanup (placeholder) |
| `health_check_job` | every 60 min | System ping |

**Resilience:** 3-attempt linear backoff retry per job. Circuit breaker trips after 5 consecutive failures — job skips until app restart. `YouTubeStructureChangedError` bypasses retry and trips circuit immediately.

---

## Middleware stack

Applied in order (Starlette registers in reverse):

1. `RateLimitMiddleware` — per-key or per-IP rate limiting
2. `AuthMiddleware` — validates `X-API-Key`
3. `LoggingMiddleware` — logs every request with duration + `X-Request-ID`
4. `IPWhitelistMiddleware` — blocks unlisted IPs (disabled by default)

---

## Environment variables

```env
PORT=8000

# API auth
API_KEYS=key1,key2

# IP whitelist
IP_WHITELIST=
IP_WHITELIST_ENABLED=false
SERVICE_TOKENS=name:token

# Proxy (optional, residential proxy improves trending HTML success rate)
PROXY_URL=
PROXY_KEYS=                     # comma-separated keys for rotating proxy provider

# Scheduler
ENABLE_SCHEDULER=true
TRENDING_CRON=0 7 * * *
SHORTS_CRON=0 9 * * *
LOCATION_CRON=0 6 * * *
KEYWORDS_CRON=0 8 * * *
CLEANUP_CRON=0 2 * * 0
HEALTH_CHECK_INTERVAL=60        # minutes

# Ingest target
INGEST_API_URL=http://localhost:3000
INGEST_SERVICE_KEY=             # must match INTERNAL_SERVICE_KEY in youtube-api
```

---

## Running locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs`
