# Phase 2: Search Engine & UI

## Goal
**"Production-grade search experience"** - Fast, relevant results with modern UI.

## Duration
2 weeks

## Success Criteria
- [ ] Integrate Meilisearch for fuzzy search
- [ ] Migrate to PostgreSQL
- [ ] HTMX-powered interactive UI
- [ ] Search result highlighting
- [ ] Auto-complete suggestions
- [ ] Mobile-responsive design

## User Stories (This Phase)
- **Story 2.1**: Typo-Tolerant Search
- **Story 2.2**: Search Highlighting
- **Story 2.3**: Real-time Search
- **Story 2.4**: Filter by Date (optional)
- **Story 2.5**: Mobile-Friendly UI

## What's New in Phase 2

### Tech Stack Changes
| Component | Phase 1 | Phase 2 |
|-----------|---------|---------|
| Database | SQLite | PostgreSQL |
| Search | SQLite FTS5 | Meilisearch |
| Frontend | Jinja2 + basic JS | Jinja2 + HTMX |
| Async | Sync | Async with asyncpg |
| Caching | None | Redis (optional) |

### New Dependencies
```
# requirements.txt additions
asyncpg==0.29.0          # Async PostgreSQL
alembic==1.13.0          # Database migrations
meilisearch-python==0.31.0  # Meilisearch client
httpx==0.25.0            # Async HTTP client
pytest-asyncio==0.21.0   # Async test support
```

## Technical Components

### 1. Database Migration (PostgreSQL)

**Migration Strategy:**
```python
# alembic/env.py
from app.database import Base
from app.models import Site, Page

target_metadata = Base.metadata
```

**SQLAlchemy Models:**
```python
# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Site(Base):
    __tablename__ = "sites"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)
    domain = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="pending")  # pending, scraping, completed, failed
    page_count = Column(Integer, default=0)
    config = Column(JSON, default=dict)  # crawl depth, selectors, etc.
    last_scraped = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = "pages"
    
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    url = Column(String, nullable=False, index=True)
    title = Column(String)
    content = Column(Text)
    metadata = Column(JSON, default=dict)  # Extracted metadata
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    site = relationship("Site", back_populates="pages")
```

**Async Database Connection:**
```python
# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

# PostgreSQL async URL
DATABASE_URL = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=settings.debug,
    pool_size=20,
    max_overflow=0,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

### 2. Meilisearch Integration

**Meilisearch Configuration:**
```python
# app/search.py
import meilisearch
from typing import List, Dict, Optional
from app.config import get_settings

settings = get_settings()

class MeiliSearchEngine:
    """Meilisearch implementation for fast, fuzzy search."""
    
    def __init__(self):
        self.client = meilisearch.Client(
            settings.meilisearch_host,
            settings.meilisearch_api_key
        )
        self.index = self.client.index("pages")
        self._ensure_index_config()
    
    def _ensure_index_config(self):
        """Configure index settings for optimal search."""
        self.index.update_settings({
            "searchableAttributes": [
                "title",
                "content",
                "url"
            ],
            "displayedAttributes": [
                "id",
                "site_id",
                "url",
                "title",
                "content",
                "metadata"
            ],
            "rankingRules": [
                "words",
                "typo",
                "proximity",
                "attribute",
                "sort",
                "exactness"
            ],
            "typoTolerance": {
                "enabled": True,
                "minWordSizeForTypos": {
                    "oneTypo": 4,
                    "twoTypos": 8
                }
            },
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "attributesToHighlight": ["title", "content"],
            "attributesToCrop": ["content"],
            "cropLength": 200
        })
    
    async def index_pages(self, pages: List[Dict]) -> None:
        """Index multiple pages in Meilisearch."""
        documents = [
            {
                "id": f"{page['site_id']}_{page['id']}",  # Composite ID
                "site_id": page["site_id"],
                "url": page["url"],
                "title": page["title"],
                "content": page["content"][:10000],  # Limit content size
                "metadata": page.get("metadata", {})
            }
            for page in pages
        ]
        
        self.index.add_documents(documents)
    
    async def search(
        self,
        query: str,
        site_id: Optional[int] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Search pages with Meilisearch.
        
        Args:
            query: Search query
            site_id: Filter by site
            limit: Results per page
            offset: Pagination offset
            
        Returns:
            Search results with highlights
        """
        filter_expr = None
        if site_id:
            filter_expr = f"site_id = {site_id}"
        
        results = self.index.search(
            query,
            {
                "limit": limit,
                "offset": offset,
                "filter": filter_expr,
                "attributesToHighlight": ["title", "content"],
                "attributesToCrop": ["content"],
                "cropLength": 200,
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>"
            }
        )
        
        return {
            "query": query,
            "total_hits": results["estimatedTotalHits"],
            "hits": [
                {
                    "id": hit["id"],
                    "site_id": hit["site_id"],
                    "url": hit["url"],
                    "title": hit["_formatted"]["title"],
                    "snippet": hit["_formatted"]["content"],
                    "rank": hit["_rankingScore"]
                }
                for hit in results["hits"]
            ],
            "processing_time_ms": results["processingTimeMs"]
        }
    
    async def delete_site_pages(self, site_id: int) -> None:
        """Delete all pages for a site."""
        self.index.delete_documents({
            "filter": f"site_id = {site_id}"
        })
```

**Docker Compose for Meilisearch:**
```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/sitesearch
      - MEILISEARCH_HOST=http://meilisearch:7700
    depends_on:
      - postgres
      - meilisearch
  
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=sitesearch
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
  
  meilisearch:
    image: getmeili/meilisearch:v1.6
    environment:
      - MEILI_MASTER_KEY=your-master-key
    volumes:
      - meili_data:/meili_data
    ports:
      - "7700:7700"

volumes:
  postgres_data:
  meili_data:
```

### 3. HTMX Frontend

**HTMX Integration:**
```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Site Search{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        /* Modern, responsive styles */
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --gray-100: #f3f4f6;
            --gray-800: #1f2937;
        }
        
        * { box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--gray-800);
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: var(--gray-100);
        }
        
        .search-container {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        
        .search-input {
            width: 100%;
            padding: 15px 20px;
            font-size: 18px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            transition: border-color 0.2s;
        }
        
        .search-input:focus {
            outline: none;
            border-color: var(--primary);
        }
        
        .results-container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
        }
        
        .result-item {
            padding: 20px;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .result-item:last-child { border-bottom: none; }
        
        .result-title {
            font-size: 18px;
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
        }
        
        .result-title:hover { text-decoration: underline; }
        
        .result-url {
            color: #059669;
            font-size: 14px;
            margin: 5px 0;
        }
        
        .result-snippet {
            color: #4b5563;
            line-height: 1.5;
        }
        
        mark {
            background: #fef08a;
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #6b7280;
        }
        
        .htmx-request .loading { display: block; }
        
        /* Mobile responsive */
        @media (max-width: 640px) {
            body { padding: 10px; }
            .search-container { padding: 20px; }
            .search-input { font-size: 16px; }
            .result-item { padding: 15px; }
        }
    </style>
</head>
<body>
    {% block content %}{% endblock %}
</body>
</html>
```

**Real-time Search Template:**
```html
<!-- templates/search.html -->
{% extends "base.html" %}
{% block title %}Search {{ site.domain }}{% endblock %}
{% block content %}
<div class="search-container">
    <h1 style="margin-top: 0;">🔍 {{ site.domain }}</h1>
    
    <form hx-get="/api/search"
          hx-target="#results"
          hx-trigger="keyup changed delay:300ms, search"
          hx-indicator="#loading">
        <input type="search"
               name="q"
               value="{{ query }}"
               placeholder="Search pages..."
               class="search-input"
               autocomplete="off">
        <input type="hidden" name="site_id" value="{{ site.id }}">
    </form>
</div>

<div id="loading" class="loading" style="display: none;">
    Searching...
</div>

<div id="results" class="results-container">
    {% include "partials/results.html" %}
</div>

<script>
// Auto-focus search input
document.querySelector('.search-input').focus();
</script>
{% endblock %}
```

**Results Partial:**
```html
<!-- templates/partials/results.html -->
{% if results %}
    <div style="margin-bottom: 15px; color: #6b7280;">
        Found {{ total_hits }} results in {{ processing_time_ms }}ms
    </div>
    
    {% for result in results %}
    <article class="result-item">
        <a href="{{ result.url }}" target="_blank" class="result-title">
            {{ result.title|safe }}
        </a>
        <div class="result-url">{{ result.url }}</div>
        <div class="result-snippet">{{ result.snippet|safe }}</div>
    </article>
    {% endfor %}
    
    {% if total_hits > results|length %}
    <div style="text-align: center; padding: 20px;">
        <button hx-get="/api/search?q={{ query }}&site_id={{ site.id }}&offset={{ results|length }}"
                hx-target="#results"
                hx-swap="beforeend"
                hx-indicator="#loading"
                style="padding: 10px 20px; background: var(--primary); color: white; border: none; border-radius: 6px; cursor: pointer;">
            Load More
        </button>
    </div>
    {% endif %}
{% elif query %}
    <div style="text-align: center; padding: 40px; color: #6b7280;">
        <p>No results found for "{{ query }}"</p>
        <p style="font-size: 14px;">Try different keywords or check your spelling</p>
    </div>
{% else %}
    <div style="text-align: center; padding: 40px; color: #6b7280;">
        <p>Start typing to search...</p>
    </div>
{% endif %}
```

### 4. Async Scraping with Progress

**Background Task Implementation:**
```python
# app/scraper.py
import asyncio
import json
from typing import AsyncIterator
from datetime import datetime
import httpx

class AsyncWebScraper:
    """Async wrapper for web-parser with progress tracking."""
    
    def __init__(self, binary_path: str = "./web-parser"):
        self.binary_path = binary_path
        self._progress_callbacks = []
    
    def on_progress(self, callback):
        """Register progress callback."""
        self._progress_callbacks.append(callback)
    
    async def _notify_progress(self, page_count: int, current_url: str):
        """Notify all progress listeners."""
        for callback in self._progress_callbacks:
            await callback(page_count, current_url)
    
    async def scrape_stream(
        self,
        url: str,
        crawl: bool = True,
        max_depth: int = 2
    ) -> AsyncIterator[dict]:
        """
        Scrape website and yield pages as they're found.
        
        Yields:
            Dict with page data: url, title, content
        """
        cmd = [
            self.binary_path,
            "-url", url,
            "-format", "json",
            "-crawl" if crawl else "",
            "-max-depth", str(max_depth),
            "-o", "-"
        ]
        cmd = [c for c in cmd if c]  # Remove empty strings
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Stream JSON output
        stdout_data = b""
        page_count = 0
        
        while True:
            chunk = await proc.stdout.read(8192)
            if not chunk:
                break
            stdout_data += chunk
            
            # Try to parse partial JSON
            try:
                data = json.loads(stdout_data)
                pages = data.get("pages", [])
                if len(pages) > page_count:
                    # New pages found
                    for page in pages[page_count:]:
                        page_count += 1
                        await self._notify_progress(page_count, page.get("url", ""))
                        yield page
            except json.JSONDecodeError:
                continue
        
        await proc.wait()
        
        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise ScrapingError(f"Scraping failed: {stderr.decode()}")
```

### 5. API Updates

**Updated Search Endpoint:**
```python
# app/main.py
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

app = FastAPI(title="Site Search API")

@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    Search indexed pages with typo tolerance and highlighting.
    
    Returns:
        Search results with highlighted snippets
    """
    search_engine = MeiliSearchEngine()
    
    results = await search_engine.search(
        query=q,
        site_id=site_id,
        limit=limit,
        offset=offset
    )
    
    return results

@app.get("/api/sites/{site_id}/progress")
async def get_scrape_progress(site_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get real-time scraping progress.
    
    Returns:
        Current status, page count, and last scraped URL
    """
    # Implementation depends on your progress tracking
    # Could use Redis, WebSockets, or Server-Sent Events
    pass
```

## Testing Criteria

### Functional Tests
- [ ] Typo-tolerant search works (e.g., "instalation" → "installation")
- [ ] Search results highlight matching terms
- [ ] Real-time search updates as user types (300ms debounce)
- [ ] Mobile layout works on screens down to 320px
- [ ] Search latency < 200ms for typical queries

### Database Migration Tests
- [ ] SQLite data migrates to PostgreSQL without loss
- [ ] All indexes created correctly
- [ ] Foreign key constraints work
- [ ] Concurrent connections handled properly

### Meilisearch Tests
- [ ] Pages index correctly with all fields
- [ ] Typo tolerance configured properly
- [ ] Highlighting works for title and content
- [ ] Filtering by site_id works
- [ ] Deleting site removes all its pages

### Performance Tests
- [ ] Search returns in < 200ms (95th percentile)
- [ ] Can handle 50 concurrent searches
- [ ] Page loads in < 1 second on 3G
- [ ] HTMX partial updates are smooth

## Migration Guide (Phase 1 → Phase 2)

### Step 1: Backup Phase 1 Data
```bash
# Export SQLite data
sqlite3 data/sites.db ".dump" > backup.sql

# Or use Python
python scripts/export_sqlite.py
```

### Step 2: Deploy PostgreSQL
```bash
# Using Docker
docker run -d \
  --name postgres \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=pass \
  -e POSTGRES_DB=sitesearch \
  -v postgres_data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:15-alpine

# Deploy Meilisearch
docker run -d \
  --name meilisearch \
  -e MEILI_MASTER_KEY=your-key \
  -v meili_data:/meili_data \
  -p 7700:7700 \
  getmeili/meilisearch:v1.6
```

### Step 3: Run Migrations
```bash
# Create migration
alembic revision --autogenerate -m "Initial migration"

# Apply migration
alembic upgrade head

# Import data
python scripts/import_to_postgres.py

# Index in Meilisearch
python scripts/index_meilisearch.py
```

### Step 4: Update Environment
```bash
# .env file updates
DATABASE_URL=postgresql://user:pass@localhost:5432/sitesearch
MEILISEARCH_HOST=http://localhost:7700
MEILISEARCH_API_KEY=your-key
```

### Step 5: Deploy Application
```bash
# Install new dependencies
pip install -r requirements.txt

# Run tests
pytest

# Start application
uvicorn app.main:app --reload
```

## Success Metrics

- **Search Performance**: 95th percentile < 200ms
- **Typo Tolerance**: 90% of typos corrected successfully
- **Mobile**: Lighthouse mobile score > 90
- **Migration**: Zero data loss, < 1 hour downtime
- **Uptime**: 99.5% during testing period

## Known Limitations (Phase 2)

1. **Single server**: No horizontal scaling yet
2. **No subdomain routing**: Still on main domain
3. **Synchronous scraping**: Large sites block for minutes
4. **No caching**: Repeated searches hit database
5. **No rate limiting**: Open to abuse

## Handoff to Phase 3

Phase 3 will address:
- Subdomain routing with wildcard SSL
- Redis + Celery for background jobs
- Real-time progress via WebSocket/SSE
- Multiple concurrent scrapes

## Deliverables

- [ ] PostgreSQL database with migrations
- [ ] Meilisearch integration
- [ ] HTMX-powered UI
- [ ] Async database operations
- [ ] Typo-tolerant search
- [ ] Mobile-responsive design
- [ ] Migration scripts (SQLite → PostgreSQL)
- [ ] Updated deployment guide
- [ ] Performance benchmarks
- [ ] Documentation (this file)

## Definition of Done

Phase 2 is complete when:
1. Database migrated to PostgreSQL
2. Meilisearch indexes all pages
3. Typo-tolerant search working
4. UI uses HTMX for interactivity
5. Mobile layout tested and working
6. Search latency consistently < 200ms
7. All Phase 1 data migrated successfully
8. Documentation updated
9. Performance tests pass
