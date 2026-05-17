# middleware

Request pipeline applied in `main.py`. Starlette processes middleware in reverse registration order, so the effective order is:

```
Request → IPWhitelistMiddleware → LoggingMiddleware → (SlowAPI/RateLimit) → AuthMiddleware (Depends) → Handler
```

Registration order in `main.py`:
```python
app.add_middleware(IPWhitelistMiddleware)   # outermost
app.add_middleware(LoggingMiddleware)       # second
# SlowAPIMiddleware is attached via app.state.limiter + exception handler
# AuthMiddleware is a FastAPI Depends, not a Starlette middleware
```

---

## `ip_whitelist.py` — IPWhitelistMiddleware

`BaseHTTPMiddleware`. Enabled only when `ENABLE_IP_WHITELIST=true` (default: `false`).

**IP check**: reads `WHITELISTED_IPS` env (comma-separated). If empty, all IPs are allowed. In `APP_ENV=development`, `127.0.0.1`, `::1`, and `localhost` are automatically added. Client IP is resolved from `X-Forwarded-For` → `X-Real-IP` → `request.client.host`.

**Service token bypass**: if the request includes both `X-Service-Name` and `X-Service-Token` headers, the middleware checks `SERVICE_TOKEN_{SERVICE_NAME}` env var. If the token matches and the service name is in `WHITELISTED_SERVICES` (comma-separated env), the request passes regardless of IP.

`/health` is always allowed through.

Blocked requests raise `HTTP 403`.

---

## `logging_middleware.py` — LoggingMiddleware

`BaseHTTPMiddleware`. Logs every request at `INFO` level.

- **On request start**: logs method, path, query params, client host.
- **On completion**: logs method, path, status code, duration.
- **On exception**: logs error with `exc_info=True` and re-raises.

Adds two response headers:
- `X-Request-ID`: millisecond timestamp string (unique per request within a second).
- `X-Process-Time`: wall-clock seconds as a string with 3 decimal places.

---

## `auth_middleware.py` — `verify_api_key`

FastAPI `Depends` (not a Starlette middleware). Applied per-router via `dependencies=[Depends(verify_api_key)]` in `routes.py` and `admin.py`.

- Reads `X-API-Key` header via `APIKeyHeader`.
- Valid keys are loaded once at startup from `API_KEYS` env (comma-separated) into `VALID_API_KEYS: set[str]`.
- Returns `HTTP 500` if `API_KEYS` is not configured.
- Returns `HTTP 401` if the header is missing.
- Returns `HTTP 403` if the key is not in `VALID_API_KEYS`.

`get_optional_api_key` is a non-raising variant that returns `None` on invalid/missing key.

---

## `rate_limit.py` — slowapi limiter

`Limiter` instance from `slowapi`, attached to `app.state.limiter`.

**Identifier function** (`get_identifier`): uses first 8 chars of `X-API-Key` prefixed with `key_`, or falls back to IP prefixed with `ip_`.

**Default limits** (applied to all routes unless overridden):
- `RATE_LIMIT_DEFAULT` env (default `100/hour`)
- `RATE_LIMIT_BURST` env (default `20/minute`)

**Storage**: `RATE_LIMIT_STORAGE` env (default `memory://`). Use a Redis URI in production.

Per-endpoint limits from `rate_limit_config.py` must be applied explicitly with `@limiter.limit(...)`. Rate limit exceeded responses use the custom `rate_limit_exceeded_handler`, which logs the identifier, path, and limit before delegating to slowapi's default handler.
