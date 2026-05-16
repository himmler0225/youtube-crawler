# youtube-crawler

FastAPI service that fetches data from the YouTube internal API and pushes it to `youtube-api` for storage.

---

## Architecture

```
APScheduler (cron jobs)
  ├── crawl_trending_videos()   → ingest_client → POST /internal/ingest/trending
  ├── crawl_location_videos()   → ingest_client → POST /internal/ingest/search
  └── crawl_popular_keywords()  → ingest_client → POST /internal/ingest/search

youtube-api (real-time requests)
  ├── GET /api/video/:id               → services/detail.py
  ├── GET /api/video/:id/comments      → services/comment.py
  └── GET /api/videos/live             → services/live.py
```

---

## Project structure

```
app/
├── api/
│   ├── routes.py                  # All FastAPI endpoints
│   └── rate_limit_config.py       # Per-endpoint rate limit config
├── config/
│   ├── urls.py                    # Base URL + proxy config
│   ├── headers.py                 # Randomized headers (User-Agent, viewport...)
│   └── logging_config.py          # JSON logger — console, app.log, error.log
├── middleware/
│   ├── auth_middleware.py          # X-API-Key authentication
│   ├── ip_whitelist.py             # IP whitelist + service token auth
│   ├── rate_limit.py               # Rate limiting (slowapi)
│   └── logging_middleware.py       # Request/response logging with requestId
├── services/
│   ├── detail.py                   # Single video detail (watch page + API fallback)
│   ├── search.py                   # Video search + pagination
│   ├── trending.py                 # Trending videos (scraped from HTML page)
│   ├── live.py                     # Live streams
│   ├── comment.py                  # Comments + replies
│   ├── shorts.py                   # Shorts feed
│   ├── channel.py                  # Channel videos
│   ├── channel_info.py             # Channel metadata (avatar, banner, subscribers)
│   ├── playlist.py                 # Channel playlists
│   └── location.py                 # Region-targeted videos via gl/hl context
├── scheduler/
│   ├── scheduler.py                # APScheduler singleton lifecycle
│   ├── config.py                   # Job schedules (cron triggers, env vars)
│   └── jobs.py                     # Job implementations (retry, circuit breaker)
├── ingest_client.py                # HTTP client that pushes data to youtube-api
├── exceptions.py                   # YouTubeStructureChangedError, CrawlNetworkError
├── types.py                        # TypedDicts for all data structures
└── utils.py                        # httpx client, proxy config, helpers
```

---

## API Endpoints

All endpoints require the `X-API-Key` header.

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
| GET | `/health` | — | Health check |

### `/api/videos/location` examples

```
GET /api/videos/location?gl=VN&hl=vi&query=Hanoi
GET /api/videos/location?gl=JP&hl=ja&query=東京&max_results=30
```

> The YouTube internal API does not support lat/lng parameters. Geographic targeting is done via the `gl` country code in the InnerTube request context.

---

## Scheduled Jobs

| Job | Cron | Description |
|-----|------|-------------|
| `crawl_trending_videos` | `0 7 * * *` | Top 100 trending → ingest/trending |
| `crawl_location_videos` | `0 6 * * *` | 26 regions (gl/hl) → ingest/search |
| `crawl_popular_keywords` | `0 8 * * *` | Fixed keyword list → ingest/search |
| `cleanup_old_data` | `0 2 * * 0` | Weekly data cleanup |
| `health_check_job` | every 60 min | System health check |

All jobs have retry logic (linear backoff, 3 attempts) and a circuit breaker that stops after 5 consecutive failures and resets after 1 hour.

---

## Middleware stack (in order)

1. `IPWhitelistMiddleware` — blocks unlisted IPs (can be disabled via env)
2. `LoggingMiddleware` — logs every request/response with requestId and duration
3. `AuthMiddleware` — validates `X-API-Key`
4. `RateLimitMiddleware` — rate limits per API key or IP

---

## Environment variables

```env
# Server
PORT=8000

# API Authentication
API_KEYS=key1,key2              # Comma-separated list of valid API keys

# IP Whitelist
IP_WHITELIST=                   # e.g. 127.0.0.1,10.0.0.1
IP_WHITELIST_ENABLED=false

# Service auth (between internal services)
SERVICE_TOKENS=name:token

# Proxy (optional)
PROXY_URL=

# Scheduler
ENABLE_SCHEDULER=true
TRENDING_CRON=0 7 * * *
LOCATION_CRON=0 6 * * *
KEYWORDS_CRON=0 8 * * *
CLEANUP_CRON=0 2 * * 0
HEALTH_CHECK_INTERVAL=60        # minutes

# Ingest (push to youtube-api)
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
