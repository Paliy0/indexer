# Phase 3: Wildcard Domains & Workers

## Goal
**"True subdomain routing"** - `fitgirl-repacks.yourdomain.com` works automatically with background job processing.

## Duration
2 weeks

## Success Criteria
- [ ] Wildcard SSL certificate (Let's Encrypt)
- [ ] Nginx reverse proxy with subdomain extraction
- [ ] Redis + Celery for background jobs
- [ ] Subdomain → site mapping
- [ ] Progress tracking during scraping
- [ ] Multiple concurrent scrapes supported

## User Stories (This Phase)
- **Story 3.1**: Subdomain Access
- **Story 3.2**: Background Scraping
- **Story 3.3**: Multiple Concurrent Scrapes
- **Story 3.4**: Re-index Site

## What's New in Phase 3

### Infrastructure Changes
| Component | Phase 2 | Phase 3 |
|-----------|---------|---------|
| Domain | Single domain | Wildcard subdomains |
| SSL | Single cert | Wildcard cert |
| Proxy | None | Nginx reverse proxy |
| Queue | None | Redis + Celery |
| Workers | Sync | Background async |
| Progress | None | Real-time updates |

### New Services
```yaml
# Added to docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
  
  worker:
    build: .
    command: celery -A app.celery worker --loglevel=info --concurrency=4
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/sitesearch
      - REDIS_URL=redis://redis:6379/0
      - MEILISEARCH_HOST=http://meilisearch:7700
    depends_on:
      - postgres
      - redis
      - meilisearch
    volumes:
      - ./web-parser:/app/web-parser
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - app
```

## Technical Components

### 1. DNS and SSL Configuration

**DNS Setup:**
```
# DNS A Record
*.yourdomain.com    A     YOUR_SERVER_IP
yourdomain.com      A     YOUR_SERVER_IP
```

**Let's Encrypt Wildcard Certificate:**
```bash
# Install certbot
certbot --version || pip install certbot

# Obtain wildcard certificate (requires DNS validation)
certbot certonly \
  --manual \
  --preferred-challenges=dns \
  -d *.yourdomain.com \
  -d yourdomain.com \
  --agree-tos \
  -m admin@yourdomain.com

# Auto-renewal setup
# Add to crontab:
0 12 * * * certbot renew --quiet
```

**Certificate Paths:**
```
/etc/letsencrypt/live/yourdomain.com/fullchain.pem
/etc/letsencrypt/live/yourdomain.com/privkey.pem
```

### 2. Nginx Reverse Proxy

**nginx.conf:**
```nginx
events {
    worker_connections 1024;
}

http {
    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=search:10m rate=30r/s;
    
    # Upstream
    upstream app {
        server app:8000;
    }
    
    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name *.yourdomain.com yourdomain.com;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 301 https://$host$request_uri;
        }
    }
    
    # HTTPS server with wildcard SSL
    server {
        listen 443 ssl http2;
        server_name *.yourdomain.com yourdomain.com;
        
        # SSL certificates
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_trusted_certificate /etc/nginx/ssl/chain.pem;
        
        # SSL settings
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;
        
        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        
        # Extract subdomain and pass to app
        location / {
            # Rate limiting
            limit_req zone=general burst=20 nodelay;
            
            proxy_pass http://app;
            proxy_http_version 1.1;
            
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Subdomain $subdomain;
            
            # WebSocket support (for SSE)
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }
        
        # Static files
        location /static/ {
            alias /app/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
        
        # Health check endpoint (no rate limit)
        location /health {
            proxy_pass http://app;
            access_log off;
        }
    }
}
```

### 3. Subdomain Extraction

**FastAPI Middleware:**
```python
# app/middleware.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import re

class SubdomainMiddleware(BaseHTTPMiddleware):
    """Extract subdomain from request and add to request state."""
    
    def __init__(self, app, base_domain: str):
        super().__init__(app)
        self.base_domain = base_domain
        self.subdomain_pattern = re.compile(rf'^([a-zA-Z0-9-]+)\.{re.escape(base_domain)}$')
    
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        
        # Check for subdomain
        match = self.subdomain_pattern.match(host)
        if match:
            subdomain = match.group(1)
            request.state.subdomain = subdomain
            request.state.is_subdomain = True
        elif host == self.base_domain:
            request.state.subdomain = None
            request.state.is_subdomain = False
        else:
            # Invalid domain
            raise HTTPException(status_code=404, detail="Domain not found")
        
        response = await call_next(request)
        return response
```

**Application Integration:**
```python
# app/main.py
from fastapi import FastAPI, Request, Depends
from app.middleware import SubdomainMiddleware
from app.config import get_settings

settings = get_settings()

app = FastAPI()

# Add subdomain middleware
app.add_middleware(
    SubdomainMiddleware,
    base_domain=settings.base_domain  # e.g., "yourdomain.com"
)

# Dependency to get subdomain
def get_subdomain(request: Request) -> str:
    return request.state.subdomain

@app.get("/")
async def root(
    subdomain: str = Depends(get_subdomain),
    db: AsyncSession = Depends(get_db)
):
    """
    Root endpoint that routes based on subdomain.
    
    If subdomain present: Show search for that site
    If no subdomain: Show landing page
    """
    if subdomain:
        # Check if site exists
        site = await get_site_by_domain(db, subdomain)
        
        if not site:
            # Site not indexed yet - show setup page
            return templates.TemplateResponse(
                "setup.html",
                {"request": request, "subdomain": subdomain}
            )
        
        if site.status == "scraping":
            # Show progress page
            return templates.TemplateResponse(
                "progress.html",
                {
                    "request": request,
                    "site": site,
                    "progress": await get_scrape_progress(site.id)
                }
            )
        
        # Show search page
        return templates.TemplateResponse(
            "search.html",
            {"request": request, "site": site}
        )
    
    # No subdomain - show landing page
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )
```

### 4. Celery Background Workers

**Celery Configuration:**
```python
# app/celery.py
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "site_search",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,  # One task at a time per worker
    broker_connection_retry_on_startup=True,
)
```

**Scrape Task:**
```python
# app/tasks.py
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from sqlalchemy.ext.asyncio import AsyncSession
from app.celery import celery_app
from app.database import AsyncSessionLocal
from app.scraper import AsyncWebScraper
from app.search import MeiliSearchEngine
from app.models import Site, Page
import asyncio

@celery_app.task(bind=True, max_retries=3)
def scrape_site_task(self, site_id: int):
    """
    Celery task to scrape a website in the background.
    
    Args:
        site_id: Database ID of the site to scrape
    """
    # Run async code in sync Celery task
    asyncio.run(_scrape_site_async(self, site_id))

async def _scrape_site_async(task, site_id: int):
    """Async implementation of scraping."""
    async with AsyncSessionLocal() as db:
        try:
            # Get site details
            site = await db.get(Site, site_id)
            if not site:
                raise ValueError(f"Site {site_id} not found")
            
            # Update status
            site.status = "scraping"
            await db.commit()
            
            # Track progress
            page_count = 0
            
            def progress_callback(count, url):
                nonlocal page_count
                page_count = count
                # Update task state for progress tracking
                task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": count,
                        "url": url,
                        "site_id": site_id
                    }
                )
                # Store in Redis for real-time updates
                import redis
                r = redis.from_url(settings.redis_url)
                r.setex(
                    f"scrape_progress:{site_id}",
                    3600,  # 1 hour TTL
                    json.dumps({"count": count, "url": url})
                )
            
            # Scrape
            scraper = AsyncWebScraper()
            scraper.on_progress(progress_callback)
            
            pages_to_index = []
            async for page_data in scraper.scrape_stream(
                url=site.url,
                crawl=True,
                max_depth=site.config.get("max_depth", 2)
            ):
                # Create page record
                page = Page(
                    site_id=site_id,
                    url=page_data["url"],
                    title=page_data.get("title", ""),
                    content=page_data.get("content", ""),
                    metadata=page_data.get("metadata", {})
                )
                db.add(page)
                await db.flush()  # Get page.id
                
                pages_to_index.append({
                    "id": page.id,
                    "site_id": site_id,
                    "url": page.url,
                    "title": page.title,
                    "content": page.content,
                    "metadata": page.metadata
                })
                
                # Batch index every 10 pages
                if len(pages_to_index) >= 10:
                    search_engine = MeiliSearchEngine()
                    await search_engine.index_pages(pages_to_index)
                    pages_to_index = []
                    await db.commit()
            
            # Index remaining pages
            if pages_to_index:
                search_engine = MeiliSearchEngine()
                await search_engine.index_pages(pages_to_index)
            
            # Update site status
            site.status = "completed"
            site.page_count = page_count
            site.last_scraped = datetime.utcnow()
            await db.commit()
            
            return {
                "site_id": site_id,
                "pages_scraped": page_count,
                "status": "completed"
            }
            
        except Exception as exc:
            # Update status to failed
            site.status = "failed"
            await db.commit()
            
            # Retry with exponential backoff
            retry_count = task.request.retries
            if retry_count < 3:
                countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s
                raise task.retry(exc=exc, countdown=countdown)
            else:
                raise MaxRetriesExceededError(f"Failed to scrape site {site_id}")
```

### 5. Real-time Progress Tracking

**Server-Sent Events (SSE) Endpoint:**
```python
# app/main.py
from fastapi.responses import StreamingResponse
import asyncio
import json

@app.get("/api/sites/{site_id}/progress/stream")
async def progress_stream(site_id: int):
    """
    Server-Sent Events endpoint for real-time scraping progress.
    
    Client connects and receives updates until scraping completes.
    """
    import redis.asyncio as redis
    
    redis_client = redis.from_url(settings.redis_url)
    
    async def event_generator():
        while True:
            # Check progress in Redis
            data = await redis_client.get(f"scrape_progress:{site_id}")
            
            if data:
                progress = json.loads(data)
                yield f"data: {json.dumps(progress)}\n\n"
                
                # Check if completed
                site = await db.get(Site, site_id)
                if site.status in ["completed", "failed"]:
                    yield f"data: {json.dumps({'status': site.status, 'done': True})}\n\n"
                    break
            
            await asyncio.sleep(1)  # Poll every second
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

**Progress Page with HTMX:**
```html
<!-- templates/progress.html -->
{% extends "base.html" %}
{% block content %}
<div class="progress-container" style="text-align: center; padding: 60px 20px;">
    <h1>Indexing {{ site.domain }}</h1>
    
    <div id="progress-info">
        <div class="spinner" style="font-size: 48px; margin: 30px 0;">⏳</div>
        <p class="status">Starting scraper...</p>
        <p class="page-count" style="color: #6b7280;">Pages found: <span id="count">0</span></p>
        <p class="current-url" style="font-size: 12px; color: #9ca3af; word-break: break-all;"></p>
    </div>
    
    <div id="complete-message" style="display: none;">
        <div style="font-size: 48px; margin: 30px 0;">✅</div>
        <h2>Indexing Complete!</h2>
        <p>Found <span id="final-count">0</span> pages</p>
        <a href="/" class="btn" style="display: inline-block; margin-top: 20px; padding: 12px 24px; background: var(--primary); color: white; text-decoration: none; border-radius: 6px;">
            Start Searching
        </a>
    </div>
</div>

<script>
// Connect to SSE endpoint
const evtSource = new EventSource("/api/sites/{{ site.id }}/progress/stream");

evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.done) {
        // Scraping complete
        document.getElementById("progress-info").style.display = "none";
        document.getElementById("complete-message").style.display = "block";
        document.getElementById("final-count").textContent = data.count || document.getElementById("count").textContent;
        evtSource.close();
        
        // Reload page after 2 seconds to show search interface
        setTimeout(() => window.location.reload(), 2000);
    } else {
        // Update progress
        document.querySelector(".status").textContent = "Scraping in progress...";
        document.getElementById("count").textContent = data.count || 0;
        document.querySelector(".current-url").textContent = data.url || "";
    }
};

evtSource.onerror = function(err) {
    console.error("SSE error:", err);
    document.querySelector(".status").textContent = "Connection lost. Please refresh.";
};
</script>
{% endblock %}
```

## Testing Criteria

### Functional Tests
- [ ] Subdomain `test.yourdomain.com` routes correctly
- [ ] SSL certificate valid for all subdomains
- [ ] HTTP redirects to HTTPS
- [ ] Background scraping continues after closing browser
- [ ] Progress updates in real-time via SSE
- [ ] Multiple scrapes can run simultaneously
- [ ] Failed scrapes retry automatically

### Infrastructure Tests
- [ ] Nginx handles 1000 concurrent connections
- [ ] Rate limiting works (blocks after 10 req/s)
- [ ] SSL auto-renewal works
- [ ] Celery workers process tasks
- [ ] Redis persists data

### Edge Cases
- [ ] Invalid subdomains return 404
- [ ] Very long subdomains handled
- [ ] Special characters in subdomains rejected
- [ ] SSL certificate expiry handled

## Deployment

### Production Docker Compose
```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.prod
    environment:
      - DATABASE_URL=postgresql://user:${DB_PASSWORD}@postgres:5432/sitesearch
      - REDIS_URL=redis://redis:6379/0
      - MEILISEARCH_HOST=http://meilisearch:7700
      - BASE_DOMAIN=yourdomain.com
    depends_on:
      - postgres
      - redis
      - meilisearch
    restart: unless-stopped
  
  worker:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: celery -A app.celery worker --loglevel=info --concurrency=4 -Q celery,scraping
    environment:
      - DATABASE_URL=postgresql://user:${DB_PASSWORD}@postgres:5432/sitesearch
      - REDIS_URL=redis://redis:6379/0
      - MEILISEARCH_HOST=http://meilisearch:7700
    depends_on:
      - postgres
      - redis
      - meilisearch
    volumes:
      - ./web-parser:/app/web-parser:ro
    restart: unless-stopped
    deploy:
      replicas: 2  # Scale workers
  
  beat:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: celery -A app.celery beat --loglevel=info
    environment:
      - DATABASE_URL=postgresql://user:${DB_PASSWORD}@postgres:5432/sitesearch
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/nginx/ssl:ro
      - ./static:/var/www/static:ro
    depends_on:
      - app
    restart: unless-stopped
  
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=sitesearch
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
  
  meilisearch:
    image: getmeili/meilisearch:v1.6
    environment:
      - MEILI_MASTER_KEY=${MEILI_KEY}
    volumes:
      - meili_data:/meili_data
    restart: unless-stopped
  
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  meili_data:
  redis_data:
```

## Success Metrics

- **Wildcard SSL**: Covers all subdomains, auto-renews
- **Subdomain Routing**: < 50ms additional latency
- **Background Jobs**: 10 concurrent scrapes
- **Progress Updates**: Real-time via SSE (< 1s delay)
- **Uptime**: 99.9% during 7-day test
- **Auto-retry**: 95% of transient failures succeed on retry

## Handoff to Phase 4

Phase 4 will add:
- Per-site configuration (CSS selectors, crawl depth)
- REST API with authentication
- Export functionality
- Search analytics
- Scheduled re-indexing

## Deliverables

- [ ] Wildcard SSL certificate
- [ ] Nginx reverse proxy config
- [ ] Subdomain extraction middleware
- [ ] Celery + Redis setup
- [ ] Background scraping tasks
- [ ] Real-time progress tracking (SSE)
- [ ] Auto-retry logic
- [ ] Production deployment config
- [ ] Monitoring dashboard (basic)
- [ ] Documentation (this file)

## Definition of Done

Phase 3 is complete when:
1. Wildcard SSL working for all subdomains
2. Subdomain routing extracts domain correctly
3. Background jobs process scrapes asynchronously
4. Real-time progress visible via SSE
5. 10 concurrent scrapes run successfully
6. Auto-retry handles transient failures
7. Production deployment tested
8. Documentation complete
