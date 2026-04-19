# YouTube Crawler - Production Setup Guide

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [API Authentication](#api-authentication)
- [Scheduled Tasks](#scheduled-tasks)
- [Integration with NestJS](#integration-with-nestjs)
- [Production Deployment](#production-deployment)

---

## 🔧 Prerequisites

- Python 3.8+
- pip or poetry
- PostgreSQL (for future database integration)
- Redis (optional, for caching)

---

## 📦 Installation

### 1. Clone the repository

```bash
cd youtube-crawler
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### 1. Create environment file

```bash
cp .env.example .env
```

### 2. Generate API keys

```bash
python -m app.utils.api_key_generator
```

Output example:
```
Generated API Keys:
--------------------------------------------------
API_KEY_1: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
API_KEY_2: x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6
API_KEY_3: p1q2r3s4t5u6v7w8x9y0z1a2b3c4d5e6
--------------------------------------------------

Add these to your .env file:
API_KEYS=key1,key2,key3
```

### 3. Update .env file

Edit `.env` and add your configuration:

```env
# API Keys (comma-separated)
API_KEYS=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6,x1y2z3a4b5c6d7e8f9g0h1i2j3k4l5m6

# Logging
LOG_LEVEL=INFO

# Scheduler
ENABLE_SCHEDULER=true
TRENDING_CRON=0 6 * * *    # Daily at 6 AM
KEYWORDS_CRON=0 8 * * *    # Daily at 8 AM
CLEANUP_CRON=0 2 * * 0     # Sunday at 2 AM

# Optional: Proxy
PROXIES=http://user:pass@proxy:port
```

---

## 🚀 Running the Application

### Development mode

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 10000
```

### Production mode

```bash
./start.sh
```

Or:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 10000 --workers 4
```

### Access the API

- API Docs: http://localhost:10000/docs
- Health Check: http://localhost:10000/health

---

## 🧪 Testing

### Run all tests

```bash
pytest
```

### Run with coverage

```bash
pytest --cov=app --cov-report=html
```

### View coverage report

```bash
open htmlcov/index.html  # On macOS
# Or browse to file:///path/to/youtube-crawler/htmlcov/index.html
```

### Run specific test categories

```bash
# Unit tests only
pytest -m unit

# API tests only
pytest -m api

# Skip slow tests
pytest -m "not slow"
```

---

## 🔐 API Authentication

All API endpoints (except `/health`) require API key authentication.

### Using cURL

```bash
curl -H "X-API-Key: your_api_key_here" \
  "http://localhost:10000/api/search?q=python+tutorial"
```

### Using Python requests

```python
import requests

headers = {"X-API-Key": "your_api_key_here"}
response = requests.get(
    "http://localhost:10000/api/search",
    params={"q": "python tutorial"},
    headers=headers
)
print(response.json())
```

### Using JavaScript/TypeScript

```typescript
const response = await fetch(
  'http://localhost:10000/api/search?q=python+tutorial',
  {
    headers: {
      'X-API-Key': 'your_api_key_here'
    }
  }
);
const data = await response.json();
```

---

## ⏰ Scheduled Tasks

The application includes automatic scheduled tasks:

### Default Schedule

| Task | Schedule | Description |
|------|----------|-------------|
| Trending Videos | Daily 6 AM | Crawl trending videos |
| Popular Keywords | Daily 8 AM | Crawl videos for predefined keywords |
| Data Cleanup | Sunday 2 AM | Clean up old data |
| Health Check | Every hour | System health check |

### Customize Schedule

Edit cron expressions in `.env`:

```env
# Run trending at 10 PM daily
TRENDING_CRON=0 22 * * *

# Run keywords every 6 hours
KEYWORDS_CRON=0 */6 * * *

# Disable scheduler entirely
ENABLE_SCHEDULER=false
```

### Cron Format

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
* * * * *
```

Examples:
- `0 6 * * *` - Daily at 6 AM
- `0 */4 * * *` - Every 4 hours
- `30 2 * * 1` - Mondays at 2:30 AM
- `0 0 1 * *` - First day of each month at midnight

---

## 🔗 Integration with NestJS

### Architecture

```
┌─────────────────┐
│   NestJS App    │
│   - Frontend    │
│   - BFF Layer   │
│   - Scheduling  │
└────────┬────────┘
         │ REST API
         ↓
┌─────────────────┐
│  FastAPI        │
│  (Crawler API)  │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  PostgreSQL     │
└─────────────────┘
```

### NestJS Service Example

```typescript
// youtube-crawler.service.ts
import { Injectable, HttpService } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class YoutubeCrawlerService {
  private readonly apiUrl: string;
  private readonly apiKey: string;

  constructor(
    private httpService: HttpService,
    private configService: ConfigService,
  ) {
    this.apiUrl = this.configService.get('CRAWLER_API_URL');
    this.apiKey = this.configService.get('CRAWLER_API_KEY');
  }

  async searchVideos(query: string, page = 1, limit = 30) {
    const { data } = await this.httpService
      .get(`${this.apiUrl}/api/search`, {
        params: { q: query, page, limit },
        headers: { 'X-API-Key': this.apiKey },
      })
      .toPromise();

    return data;
  }

  async getVideoDetail(videoId: string) {
    const { data } = await this.httpService
      .get(`${this.apiUrl}/api/video/${videoId}`, {
        headers: { 'X-API-Key': this.apiKey },
      })
      .toPromise();

    return data;
  }
}
```

### NestJS Scheduled Task Example

```typescript
// crawler.scheduler.ts
import { Injectable } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { YoutubeCrawlerService } from './youtube-crawler.service';

@Injectable()
export class CrawlerScheduler {
  constructor(
    private youtubeCrawlerService: YoutubeCrawlerService,
  ) {}

  @Cron(CronExpression.EVERY_DAY_AT_6AM)
  async crawlTrendingVideos() {
    console.log('Starting trending videos crawl...');
    const trending = await this.youtubeCrawlerService.getTrending();
    // Save to database
    await this.saveTrendingVideos(trending);
  }

  @Cron(CronExpression.EVERY_6_HOURS)
  async crawlPopularKeywords() {
    const keywords = ['python', 'javascript', 'react'];
    for (const keyword of keywords) {
      const videos = await this.youtubeCrawlerService.searchVideos(keyword);
      // Save to database
      await this.saveKeywordVideos(keyword, videos);
    }
  }
}
```

---

## 🌐 Production Deployment

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  youtube-crawler:
    build: .
    ports:
      - "10000:10000"
    environment:
      - LOG_LEVEL=INFO
      - ENABLE_SCHEDULER=true
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
```

Run:

```bash
docker-compose up -d
```

### Environment Variables for Production

```env
# Production settings
APP_ENV=production
LOG_LEVEL=WARNING
ENABLE_SCHEDULER=true

# Use secrets manager for these in production
API_KEYS=${SECRET_API_KEYS}
PROXIES=${SECRET_PROXY_URL}
```

### Health Monitoring

Setup monitoring for `/health` endpoint:

```bash
curl http://localhost:10000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "youtube-crawler",
  "version": "1.0.0"
}
```

---

## 📊 Logging

Logs are stored in the `logs/` directory:

- `app.log` - All application logs (JSON format)
- `error.log` - Error logs only (JSON format)

View real-time logs:

```bash
tail -f logs/app.log | jq .
```

---

## 🔒 Security Checklist

- [ ] API keys are stored in environment variables
- [ ] `.env` file is not committed to git
- [ ] CORS origins are properly configured
- [ ] Rate limiting is configured (future)
- [ ] HTTPS is enabled in production
- [ ] Logs don't contain sensitive data
- [ ] Database credentials are secured
- [ ] Proxy credentials are in secrets manager

---

## 📈 Next Steps

1. **Database Integration**
   - Setup PostgreSQL
   - Create Prisma/SQLAlchemy schema
   - Implement data persistence

2. **Caching**
   - Setup Redis
   - Implement response caching
   - Add rate limiting

3. **Monitoring**
   - Setup Sentry for error tracking
   - Add Prometheus metrics
   - Configure alerts

4. **CI/CD**
   - Setup GitHub Actions
   - Add automated testing
   - Deploy to production

---

## 🆘 Troubleshooting

### API returns 401 Unauthorized

- Check that `X-API-Key` header is set
- Verify API key is in `.env` file under `API_KEYS`

### Scheduler not running

- Check `ENABLE_SCHEDULER=true` in `.env`
- Check logs for scheduler startup messages
- Verify cron expressions are valid

### Tests failing

```bash
# Clear pytest cache
pytest --cache-clear

# Run with verbose output
pytest -v

# Check specific test
pytest tests/test_api.py::TestHealthEndpoint::test_health_check -v
```

---

## 📞 Support

For issues or questions, please check:
- Application logs in `logs/` directory
- API documentation at `/docs` endpoint
- Test coverage report in `htmlcov/`
