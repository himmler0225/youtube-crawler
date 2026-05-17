# scheduler

APScheduler-based job runner. Crawls YouTube on a schedule and pushes results to youtube-api via `ingest_client`.

## Files

| File | Role |
|------|------|
| `scheduler.py` | `AsyncIOScheduler` singleton (`get_scheduler()`), `start_scheduler()`, `shutdown_scheduler()` |
| `config.py` | `configure_jobs()` — registers all jobs into the scheduler; called once in FastAPI lifespan |
| `jobs.py` | Job function implementations |

## Jobs

| Job ID | Default cron | What it does |
|--------|-------------|--------------|
| `crawl_trending` | `0 7 * * *` | HTML-scrapes `/feed/trending`; falls back to search-by-view-count if HTML returns empty or raises `YouTubeStructureChangedError`. Posts to `POST /internal/ingest/trending`. |
| `crawl_shorts` | `0 9 * * *` | Crawls Shorts feed via InnerTube `reel/reel_item_watch` + search shelf. Posts to `POST /internal/ingest/shorts` (separate `shorts` table, not `videos`). |
| `crawl_location` | `0 6 * * *` | Searches 26 cities with per-city `gl`/`hl` context. Posts to `POST /internal/ingest/search` with `query="location:{city}"`. Runs earliest because it takes the longest (~26 requests). |
| `crawl_keywords` | `0 8 * * *` | Searches a fixed tech keyword list (`python tutorial`, `fastapi`, `react tutorial`, `nodejs`, `machine learning`) sorted by `upload_date`. Posts to `POST /internal/ingest/search`. |
| `cleanup_data` | `0 2 * * 0` | Placeholder — no delete logic yet. Intended for purging stale `SearchResult` / `TrendingSnapshot` rows. |
| `health_check` | every 60 min | Logs a DEBUG ping to confirm the scheduler is alive. |

All cron strings are overridable via env vars (`TRENDING_CRON`, `SHORTS_CRON`, `LOCATION_CRON`, `KEYWORDS_CRON`, `CLEANUP_CRON`). The health check interval is controlled by `HEALTH_CHECK_INTERVAL` (minutes, default 60).

Set `ENABLE_SCHEDULER=false` to start the app in API-only mode without registering any jobs.

Each job is registered with `max_instances=1` to prevent overlapping runs if a job overruns its cron window.

## Circuit Breaker

Implemented per-job in `jobs.py` using `_failure_counts: dict[str, int]`.

- **Threshold**: `MAX_CONSECUTIVE_FAILURES = 5`
- **Open**: `_is_circuit_open(job_id)` returns `True` when failure count >= threshold. The job logs `CRITICAL` and returns `{"success": False, "error": "circuit_open"}` immediately.
- **Reset**: `_record_success(job_id)` sets the counter back to 0 after any successful run. There is no automatic time-based reset — a successful run (or app restart) is required.
- `YouTubeStructureChangedError` increments the circuit breaker counter immediately (no retry).

## Retry (`_with_retry`)

Wraps individual YouTube service calls within a job.

- Max 3 attempts, linear backoff: attempt 1 waits 2 s, attempt 2 waits 4 s, attempt 3 raises.
- `YouTubeStructureChangedError` is re-raised immediately — retrying a structural parse failure is pointless.

## Batch Concurrency (location & keywords jobs)

- `asyncio.Semaphore(BATCH_CONCURRENCY=3)` caps concurrent YouTube requests to 3.
- Random stagger of 0–1.5 s (location) / 0–1.0 s (keywords) inside the semaphore to avoid burst rate-limiting.
- `asyncio.gather(*tasks, return_exceptions=True)` — a single city/keyword failure does not cancel the rest.
- If any exception in the results is a `YouTubeStructureChangedError`, it is re-raised after gather completes to trigger the circuit breaker.

## Location Targets

26 cities across Southeast Asia, East Asia, South Asia, Middle East, Europe, North/South America, Africa, and Oceania. Each entry carries `name`, `gl` (country code), `hl` (language code), and `query` (local-language city name). Defined as `LOCATION_TARGETS` list in `jobs.py`.
