# Security & Rate Limiting Guide

## 🔒 Overview

YouTube Crawler API được bảo vệ bởi nhiều lớp security:

1. **API Key Authentication** - Xác thực requests
2. **Rate Limiting** - Giới hạn số lượng requests
3. **IP Whitelist** - Chỉ cho phép IPs/services cụ thể
4. **Service-to-Service Authentication** - Token-based auth cho services

---

## 🔑 1. API Key Authentication

### Setup API Keys

```bash
# Generate API keys
python -m app.utils.api_key_generator
```

Output:
```
API_KEY_1: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
API_KEY_2: x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6
```

### Configure in .env

```env
API_KEYS=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6,x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6
```

### Usage

All API endpoints (except `/health`) require the `X-API-Key` header:

```bash
curl -H "X-API-Key: your_api_key_here" \
  "http://localhost:10000/api/search?q=python"
```

---

## ⏱️ 2. Rate Limiting

### Default Limits

| Scope | Limit | Description |
|-------|-------|-------------|
| Global | 100/hour | Default limit for all endpoints |
| Burst | 20/minute | Short-term burst protection |

### Endpoint-Specific Limits

Configure in [app/api/rate_limit_config.py](app/api/rate_limit_config.py):

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `/search` | 30/minute | Moderate usage |
| `/video/*` | 60/minute | High frequency access |
| `/channel/videos` | 10/minute | Heavy payload |
| `/comments` | 15/minute | Recursive, expensive |
| `/location` | 5/minute | Very expensive |

### Configuration

```env
# Default rate limit
RATE_LIMIT_DEFAULT=100/hour

# Burst protection
RATE_LIMIT_BURST=20/minute

# Storage backend (use Redis in production)
RATE_LIMIT_STORAGE=redis://localhost:6379/1
```

### Response Headers

Rate limit info được trả về trong response headers:

```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 28
X-RateLimit-Reset: 1640000000
```

### 429 Too Many Requests

Khi vượt quá rate limit:

```json
{
  "detail": "Rate limit exceeded: 30 per 1 minute"
}
```

### Rate Limiting Strategies

**Per API Key:**
- Mỗi API key có rate limit riêng
- Identifier: `key_{first_8_chars_of_api_key}`

**Per IP Address:**
- Unauthenticated requests: rate limit theo IP
- Identifier: `ip_{ip_address}`

---

## 🌐 3. IP Whitelist

### Enable IP Whitelist

```env
ENABLE_IP_WHITELIST=true
```

### Configure Allowed IPs

```env
# Single IPs (comma-separated)
WHITELISTED_IPS=192.168.1.100,192.168.1.101

# CIDR notation for IP ranges
WHITELISTED_IPS=10.0.0.0/8,172.16.0.0/12

# Mix of both
WHITELISTED_IPS=192.168.1.100,10.0.0.0/8,172.17.0.2
```

### Development Mode

In development (`APP_ENV=development`), localhost is automatically whitelisted:
- `127.0.0.1`
- `::1`
- `localhost`

### Behind Proxy/Load Balancer

API automatically checks these headers:
1. `X-Forwarded-For` (from reverse proxy)
2. `X-Real-IP` (from nginx)
3. Direct connection IP

---

## 🔐 4. Service-to-Service Authentication

### For NestJS Integration

#### Step 1: Configure Service

```env
# In YouTube Crawler .env
WHITELISTED_SERVICES=youtube-api
SERVICE_TOKEN_YOUTUBE_API=secure_random_token_here
```

#### Step 2: NestJS Request Headers

```typescript
// In your NestJS service
const headers = {
  'X-API-Key': process.env.CRAWLER_API_KEY,
  'X-Service-Name': 'youtube-api',
  'X-Service-Token': process.env.CRAWLER_SERVICE_TOKEN,
};

const response = await axios.get(
  'http://crawler-api:10000/api/search',
  {
    params: { q: 'python' },
    headers
  }
);
```

#### Step 3: Higher Rate Limits for Services

Services in whitelist get higher rate limits:

```python
# app/api/rate_limit_config.py
SERVICE_RATE_LIMITS = {
    "youtube-api": "200/minute",  # Your NestJS app
    "default": "50/minute",
}
```

---

## 🏗️ Architecture Flow

```
┌──────────────┐
│  NestJS API  │
└──────┬───────┘
       │ Headers:
       │ - X-API-Key: xxx
       │ - X-Service-Name: youtube-api
       │ - X-Service-Token: yyy
       ↓
┌──────────────────────────────────┐
│  YouTube Crawler API             │
│                                  │
│  1. IP Whitelist Check ✓         │
│     ↓                            │
│  2. Service Token Verify ✓       │
│     ↓                            │
│  3. API Key Auth ✓               │
│     ↓                            │
│  4. Rate Limit Check ✓           │
│     ↓                            │
│  5. Process Request              │
└──────────────────────────────────┘
```

---

## 🚀 Production Setup

### 1. Enable All Security Features

```env
# Enable IP whitelist
ENABLE_IP_WHITELIST=true

# Set production IPs
WHITELISTED_IPS=<your_nestjs_server_ip>

# Configure services
WHITELISTED_SERVICES=youtube-api
SERVICE_TOKEN_YOUTUBE_API=<generate_strong_token>

# Use Redis for rate limiting
RATE_LIMIT_STORAGE=redis://redis:6379/1

# Strict rate limits
RATE_LIMIT_DEFAULT=50/hour
RATE_LIMIT_BURST=10/minute
```

### 2. Generate Secure Tokens

```bash
# Generate service token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Setup Redis (for distributed rate limiting)

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  youtube-crawler:
    environment:
      - RATE_LIMIT_STORAGE=redis://redis:6379/1
```

---

## 📊 Monitoring

### Rate Limit Logs

Logs được ghi vào `logs/app.log`:

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "level": "WARNING",
  "message": "Rate limit exceeded",
  "extra": {
    "identifier": "key_a1b2c3d4",
    "path": "/api/search",
    "limit": "30 per 1 minute"
  }
}
```

### IP Whitelist Violations

```json
{
  "timestamp": "2024-01-01T12:00:00",
  "level": "WARNING",
  "message": "Blocked request from non-whitelisted source",
  "extra": {
    "ip": "203.0.113.42",
    "service": null,
    "path": "/api/search"
  }
}
```

---

## 🧪 Testing

### Test Rate Limiting

```bash
# Spam requests to trigger rate limit
for i in {1..35}; do
  curl -H "X-API-Key: your_key" \
    "http://localhost:10000/api/search?q=test"
done

# Should get 429 after 30 requests
```

### Test IP Whitelist

```bash
# From non-whitelisted IP
curl "http://localhost:10000/api/search?q=test"
# Expected: 403 Forbidden
```

### Test Service Authentication

```bash
# Valid service token
curl -H "X-Service-Name: youtube-api" \
     -H "X-Service-Token: valid_token" \
     -H "X-API-Key: your_key" \
     "http://localhost:10000/api/search?q=test"
# Expected: 200 OK

# Invalid service token
curl -H "X-Service-Name: youtube-api" \
     -H "X-Service-Token: wrong_token" \
     -H "X-API-Key: your_key" \
     "http://localhost:10000/api/search?q=test"
# Expected: 403 Forbidden
```

---

## 🔧 Troubleshooting

### Rate Limit Too Strict

```env
# Increase limits
RATE_LIMIT_DEFAULT=200/hour
RATE_LIMIT_BURST=50/minute
```

### Service Can't Connect

1. Check IP whitelist: `WHITELISTED_IPS=<service_ip>`
2. Verify service token: `SERVICE_TOKEN_YOUTUBE_API=<correct_token>`
3. Check logs: `tail -f logs/app.log`

### Redis Connection Issues

```env
# Fallback to in-memory
RATE_LIMIT_STORAGE=memory://
```

---

## 🎯 NestJS Integration Example

### Full Service Class

```typescript
// youtube-crawler.service.ts
import { Injectable, HttpService } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class YoutubeCrawlerService {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly serviceName: string;
  private readonly serviceToken: string;

  constructor(
    private httpService: HttpService,
    private configService: ConfigService,
  ) {
    this.baseUrl = this.configService.get('CRAWLER_API_URL');
    this.apiKey = this.configService.get('CRAWLER_API_KEY');
    this.serviceName = 'youtube-api';
    this.serviceToken = this.configService.get('CRAWLER_SERVICE_TOKEN');
  }

  private getHeaders() {
    return {
      'X-API-Key': this.apiKey,
      'X-Service-Name': this.serviceName,
      'X-Service-Token': this.serviceToken,
    };
  }

  async searchVideos(query: string) {
    const { data } = await this.httpService
      .get(`${this.baseUrl}/api/search`, {
        params: { q: query },
        headers: this.getHeaders(),
      })
      .toPromise();

    return data;
  }

  async getVideoDetail(videoId: string) {
    const { data } = await this.httpService
      .get(`${this.baseUrl}/api/video/${videoId}`, {
        headers: this.getHeaders(),
      })
      .toPromise();

    return data;
  }
}
```

### NestJS Environment Variables

```env
# .env in NestJS app
CRAWLER_API_URL=http://youtube-crawler:10000
CRAWLER_API_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
CRAWLER_SERVICE_TOKEN=secure_service_token_here
```

---

## 📚 Best Practices

1. **Always use HTTPS in production**
2. **Rotate API keys periodically**
3. **Use Redis for distributed systems**
4. **Monitor rate limit violations**
5. **Keep service tokens secret**
6. **Use environment-specific configs**
7. **Enable IP whitelist in production**
8. **Log all security events**

---

## 🆘 Support

Nếu có vấn đề:
1. Check logs: `logs/app.log`
2. Verify config: `.env` file
3. Test endpoints: `/health` check
4. Review security logs for blocked requests
