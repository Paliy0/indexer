# Phase 4: Advanced Features

## Goal
**"Power user features"** - Custom configuration, API access, exports, and analytics.

## Duration
2 weeks

## Success Criteria
- [ ] Per-site configuration (selectors, crawl depth)
- [ ] REST API with API keys
- [ ] Export results (JSON/CSV/Markdown)
- [ ] Scheduled re-indexing
- [ ] Search analytics dashboard
- [ ] API rate limiting

## User Stories (This Phase)
- **Story 4.1**: Custom CSS Selectors
- **Story 4.2**: REST API
- **Story 4.3**: Export Results
- **Story 4.4**: Search Analytics
- **Story 4.5**: API Access (key management)

## What's New in Phase 4

### Features Added
| Feature | Description | Priority |
|---------|-------------|----------|
| Site Config | Per-site CSS selectors, crawl depth, exclusions | High |
| REST API | Full programmatic access with auth | High |
| Exports | Download search results | Medium |
| Analytics | Search query tracking | Medium |
| Scheduling | Auto re-index sites | Medium |
| API Keys | Authentication system | High |

### API Version
```
/api/v1/          # New versioned API
/api/search       # Legacy (backward compatible)
```

## Technical Components

### 1. Site Configuration System

**Configuration Schema:**
```python
# app/models.py additions
class SiteConfig(BaseModel):
    """Site-specific configuration."""
    
    # Content selection
    content_selector: str = "body"  # CSS selector for main content
    title_selector: str = "title"   # CSS selector for page title
    exclude_selectors: List[str] = []  # CSS selectors to exclude (ads, nav)
    
    # Crawling options
    max_depth: int = 2              # Maximum crawl depth
    delay_ms: int = 100             # Delay between requests
    respect_robots_txt: bool = True
    
    # URL filtering
    include_patterns: List[str] = [".*"]  # Regex patterns to include
    exclude_patterns: List[str] = []      # Regex patterns to exclude
    
    # Auto-refresh
    auto_reindex: bool = False      # Enable scheduled re-indexing
    reindex_interval_days: int = 7  # Days between re-indexes
    
    # Advanced
    custom_headers: Dict[str, str] = {}  # Custom HTTP headers
    user_agent: Optional[str] = None     # Custom user agent

class Site(Base):
    __tablename__ = "sites"
    
    # ... existing columns ...
    config: Column(JSON, default=lambda: SiteConfig().dict())
```

**Configuration UI:**
```html
<!-- templates/config.html -->
{% extends "base.html" %}
{% block content %}
<div class="config-container">
    <h1>Configure {{ site.domain }}</h1>
    
    <form id="config-form" hx-post="/api/sites/{{ site.id }}/config" hx-swap="none">
        <section>
            <h3>Content Selection</h3>
            <label>
                Content CSS Selector
                <input type="text" name="content_selector" 
                       value="{{ config.content_selector }}"
                       placeholder="e.g., .content, #main, article">
                <small>CSS selector for the main content area</small>
            </label>
            
            <label>
                Title CSS Selector
                <input type="text" name="title_selector"
                       value="{{ config.title_selector }}">
            </label>
            
            <label>
                Exclude Selectors (one per line)
                <textarea name="exclude_selectors" rows="3">{{ config.exclude_selectors|join('\n') }}</textarea>
                <small>Elements to exclude (ads, navigation, etc.)</small>
            </label>
        </section>
        
        <section>
            <h3>Crawling Options</h3>
            <label>
                Max Crawl Depth
                <input type="number" name="max_depth" 
                       value="{{ config.max_depth }}" min="1" max="5">
            </label>
            
            <label>
                Request Delay (ms)
                <input type="number" name="delay_ms"
                       value="{{ config.delay_ms }}" min="50" max="5000">
            </label>
        </section>
        
        <section>
            <h3>URL Filtering</h3>
            <label>
                Include Patterns (regex, one per line)
                <textarea name="include_patterns" rows="3">{{ config.include_patterns|join('\n') }}</textarea>
            </label>
            
            <label>
                Exclude Patterns (regex, one per line)
                <textarea name="exclude_patterns" rows="3">{{ config.exclude_patterns|join('\n') }}</textarea>
            </label>
        </section>
        
        <section>
            <h3>Auto-Refresh</h3>
            <label class="checkbox">
                <input type="checkbox" name="auto_reindex" 
                       {% if config.auto_reindex %}checked{% endif %}>
                Enable automatic re-indexing
            </label>
            
            <label>
                Re-index Interval (days)
                <input type="number" name="reindex_interval_days"
                       value="{{ config.reindex_interval_days }}" min="1" max="30">
            </label>
        </section>
        
        <button type="submit" class="btn-primary">Save Configuration</button>
        <button type="button" class="btn-secondary" 
                hx-post="/api/sites/{{ site.id }}/preview"
                hx-target="#preview">
            Preview Selector
        </button>
    </form>
    
    <div id="preview"></div>
</div>

<style>
.config-container { max-width: 600px; }
section { margin: 30px 0; padding: 20px; background: #f9fafb; border-radius: 8px; }
label { display: block; margin: 15px 0; }
input, textarea { width: 100%; padding: 8px; margin-top: 5px; }
small { color: #6b7280; font-size: 12px; }
.checkbox { display: flex; align-items: center; gap: 8px; }
.checkbox input { width: auto; }
</style>
{% endblock %}
```

**Preview Endpoint:**
```python
@app.post("/api/sites/{site_id}/preview")
async def preview_selector(
    site_id: int,
    content_selector: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview what content will be extracted with given selector.
    
    Fetches first page of site and shows extracted content.
    """
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    
    # Fetch first page
    async with httpx.AsyncClient() as client:
        response = await client.get(site.url, timeout=30)
        html = response.text
    
    # Extract with selector
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    elements = soup.select(content_selector)
    
    if not elements:
        return HTMLResponse("<p style='color: red;'>No elements found with that selector</p>")
    
    # Show preview
    preview_html = f"""
    <div style="border: 2px solid #2563eb; padding: 15px; margin-top: 20px;">
        <h4>Preview (found {len(elements)} elements)</h4>
        <div style="max-height: 300px; overflow: auto; background: #f3f4f6; padding: 10px;">
            {elements[0].prettify()[:2000]}
        </div>
        <p style="color: #6b7280; font-size: 12px;">
            Showing first element only. {len(elements)} total found.
        </p>
    </div>
    """
    
    return HTMLResponse(preview_html)
```

### 2. API Key Authentication

**API Key Model:**
```python
# app/models.py
class APIKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True)
    key_hash = Column(String, unique=True, nullable=False)  # Store hash only!
    name = Column(String)  # User-provided name
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)  # Optional: restrict to site
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=100)
    
    # Usage tracking
    requests_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

class APIRequest(Base):
    """Log all API requests for analytics."""
    __tablename__ = "api_requests"
    
    id = Column(Integer, primary_key=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"))
    endpoint = Column(String)
    method = Column(String)
    status_code = Column(Integer)
    response_time_ms = Column(Integer)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
```

**API Key Generation:**
```python
# app/auth.py
import secrets
import hashlib
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def generate_api_key() -> str:
    """Generate a new API key."""
    # Format: prefix_randomstring
    return f"ss_{secrets.token_urlsafe(32)}"

def hash_api_key(key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """
    Verify API key from Authorization header.
    
    Format: Authorization: Bearer ss_xxxxx
    """
    token = credentials.credentials
    
    if not token.startswith("ss_"):
        raise HTTPException(status_code=401, detail="Invalid API key format")
    
    # Hash and look up
    key_hash = hash_api_key(token)
    
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
            or_(
                APIKey.expires_at.is_(None),
                APIKey.expires_at > datetime.utcnow()
            )
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    # Update usage stats
    api_key.requests_count += 1
    api_key.last_used_at = datetime.utcnow()
    await db.commit()
    
    return api_key
```

**Rate Limiting:**
```python
# app/rate_limit.py
from fastapi import HTTPException
from datetime import datetime, timedelta
import redis

class RateLimiter:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int = 60  # seconds
    ):
        """
        Check if request is within rate limit.
        
        Args:
            key: Unique identifier (e.g., api_key_id)
            limit: Max requests per window
            window: Time window in seconds
            
        Raises:
            HTTPException: If rate limit exceeded
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window)
        
        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(f"ratelimit:{key}", 0, window_start.timestamp())
        
        # Count current entries
        pipe.zcard(f"ratelimit:{key}")
        
        # Add current request
        pipe.zadd(f"ratelimit:{key}", {str(now.timestamp()): now.timestamp()})
        
        # Set expiry on the key
        pipe.expire(f"ratelimit:{key}", window)
        
        results = pipe.execute()
        current_count = results[1]
        
        if current_count >= limit:
            # Get retry-after time
            oldest = self.redis.zrange(f"ratelimit:{key}", 0, 0, withscores=True)
            if oldest:
                retry_after = int(oldest[0][1] + window - now.timestamp())
            else:
                retry_after = window
            
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)}
            )
```

### 3. REST API v1

**API Endpoints:**
```python
# app/api/v1/router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

router = APIRouter(prefix="/api/v1")

# Sites
@router.get("/sites")
async def list_sites(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """List all indexed sites."""
    query = select(Site).offset(skip).limit(limit)
    
    if api_key.site_id:
        query = query.where(Site.id == api_key.site_id)
    
    result = await db.execute(query)
    sites = result.scalars().all()
    
    return {
        "sites": [{
            "id": s.id,
            "url": s.url,
            "domain": s.domain,
            "status": s.status,
            "page_count": s.page_count,
            "last_scraped": s.last_scraped
        } for s in sites]
    }

@router.post("/sites")
async def create_site(
    url: str,
    crawl: bool = True,
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Submit a new site for indexing."""
    # Validate URL
    # Create site record
    # Queue scraping task
    pass

@router.get("/sites/{site_id}")
async def get_site(
    site_id: int,
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Get site details."""
    pass

@router.post("/sites/{site_id}/reindex")
async def reindex_site(
    site_id: int,
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Trigger re-indexing of a site."""
    pass

# Search
@router.get("/search")
async def api_search(
    q: str = Query(..., min_length=1, description="Search query"),
    site_id: Optional[int] = Query(None, description="Filter by site"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    highlight: bool = Query(True, description="Highlight matches"),
    api_key: APIKey = Depends(verify_api_key),
    rate_limiter: RateLimiter = Depends(get_rate_limiter)
):
    """
    Search indexed pages.
    
    Returns paginated results with highlighted snippets.
    """
    # Check rate limit
    await rate_limiter.check_rate_limit(
        f"api:{api_key.id}",
        limit=api_key.rate_limit_per_minute
    )
    
    # Check site restriction
    if api_key.site_id and site_id != api_key.site_id:
        raise HTTPException(status_code=403, detail="Not authorized for this site")
    
    # Perform search
    search_engine = MeiliSearchEngine()
    results = await search_engine.search(
        query=q,
        site_id=site_id,
        limit=limit,
        offset=offset
    )
    
    return results

@router.get("/search/suggest")
async def search_suggestions(
    q: str = Query(..., min_length=2),
    site_id: Optional[int] = None,
    limit: int = Query(5, ge=1, le=10),
    api_key: APIKey = Depends(verify_api_key)
):
    """Get search suggestions (autocomplete)."""
    pass

# Exports
@router.get("/sites/{site_id}/export")
async def export_site(
    site_id: int,
    format: str = Query("json", regex="^(json|csv|md)$"),
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Export all pages from a site.
    
    Formats:
    - json: Full data as JSON
    - csv: Spreadsheet format
    - md: Markdown format for documentation
    """
    pass
```

### 4. Export Functionality

**Export Formats:**
```python
# app/export.py
from typing import List, Dict
import csv
import json
import io

class Exporter:
    """Export search results in various formats."""
    
    @staticmethod
    def to_json(pages: List[Dict]) -> str:
        """Export to JSON format."""
        return json.dumps({
            "exported_at": datetime.utcnow().isoformat(),
            "total_pages": len(pages),
            "pages": pages
        }, indent=2)
    
    @staticmethod
    def to_csv(pages: List[Dict]) -> str:
        """Export to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["url", "title", "content_preview", "indexed_at"])
        
        # Data
        for page in pages:
            writer.writerow([
                page["url"],
                page["title"],
                page["content"][:200] + "..." if len(page["content"]) > 200 else page["content"],
                page["indexed_at"]
            ])
        
        return output.getvalue()
    
    @staticmethod
    def to_markdown(pages: List[Dict]) -> str:
        """Export to Markdown format."""
        lines = [
            "# Site Export",
            "",
            f"Exported: {datetime.utcnow().isoformat()}",
            f"Total pages: {len(pages)}",
            "",
            "---",
            ""
        ]
        
        for page in pages:
            lines.extend([
                f"## {page['title']}",
                "",
                f"**URL:** {page['url']}",
                "",
                page["content"],
                "",
                "---",
                ""
            ])
        
        return "\n".join(lines)
```

### 5. Analytics Dashboard

**Analytics Queries:**
```python
# app/analytics.py
from sqlalchemy import func, desc
from datetime import datetime, timedelta

class Analytics:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_search_stats(
        self,
        site_id: Optional[int] = None,
        days: int = 30
    ) -> Dict:
        """Get search analytics for a site."""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Total searches
        total_query = select(func.count(SearchQuery.id)).where(
            SearchQuery.timestamp >= since
        )
        if site_id:
            total_query = total_query.where(SearchQuery.site_id == site_id)
        total = await self.db.scalar(total_query)
        
        # Top queries
        top_queries = await self.db.execute(
            select(
                SearchQuery.query,
                func.count(SearchQuery.id).label("count")
            )
            .where(SearchQuery.timestamp >= since)
            .where(SearchQuery.site_id == site_id if site_id else True)
            .group_by(SearchQuery.query)
            .order_by(desc("count"))
            .limit(20)
        )
        
        # Failed searches (no results)
        failed = await self.db.scalar(
            select(func.count(SearchQuery.id)).where(
                SearchQuery.timestamp >= since,
                SearchQuery.results_count == 0
            )
        )
        
        # Average results per query
        avg_results = await self.db.scalar(
            select(func.avg(SearchQuery.results_count)).where(
                SearchQuery.timestamp >= since
            )
        )
        
        return {
            "period_days": days,
            "total_searches": total,
            "failed_searches": failed,
            "avg_results_per_query": round(avg_results or 0, 2),
            "top_queries": [{"query": q, "count": c} for q, c in top_queries],
            "searches_by_day": await self._get_searches_by_day(site_id, since)
        }
    
    async def _get_searches_by_day(
        self,
        site_id: Optional[int],
        since: datetime
    ) -> List[Dict]:
        """Get search counts grouped by day."""
        result = await self.db.execute(
            select(
                func.date(SearchQuery.timestamp).label("date"),
                func.count(SearchQuery.id).label("count")
            )
            .where(SearchQuery.timestamp >= since)
            .where(SearchQuery.site_id == site_id if site_id else True)
            .group_by("date")
            .order_by("date")
        )
        
        return [{"date": d, "count": c} for d, c in result]
```

### 6. Scheduled Re-indexing

**Celery Beat Schedule:**
```python
# app/celery.py
celery_app.conf.beat_schedule = {
    "check-auto-reindex": {
        "task": "app.tasks.check_auto_reindex",
        "schedule": 3600.0,  # Every hour
    },
}

# app/tasks.py
@celery_app.task
def check_auto_reindex():
    """
    Check for sites due for re-indexing and queue them.
    
    Runs every hour via Celery Beat.
    """
    asyncio.run(_check_auto_reindex_async())

async def _check_auto_reindex_async():
    async with AsyncSessionLocal() as db:
        # Find sites with auto_reindex enabled
        # and last_scraped > reindex_interval_days
        threshold = datetime.utcnow() - timedelta(days=1)  # Check daily
        
        result = await db.execute(
            select(Site).where(
                Site.config["auto_reindex"].as_boolean() == True,
                Site.status == "completed",
                or_(
                    Site.last_scraped.is_(None),
                    Site.last_scraped <= threshold
                )
            )
        )
        
        sites = result.scalars().all()
        
        for site in sites:
            # Check if enough time has passed
            interval = site.config.get("reindex_interval_days", 7)
            due_date = site.last_scraped + timedelta(days=interval)
            
            if datetime.utcnow() >= due_date:
                # Queue re-index
                scrape_site_task.delay(site.id)
                logger.info(f"Auto re-index queued for {site.domain}")
```

## Testing Criteria

### API Tests
- [ ] API key authentication works
- [ ] Rate limiting blocks excessive requests
- [ ] All v1 endpoints return correct format
- [ ] Site-restricted keys work correctly
- [ ] API key can be revoked

### Configuration Tests
- [ ] Custom CSS selectors extract correct content
- [ ] Preview shows accurate extraction
- [ ] Exclude patterns work
- [ ] Max depth respected
- [ ] Config persists after update

### Export Tests
- [ ] JSON export contains all fields
- [ ] CSV export opens in Excel/sheets
- [ ] Markdown export renders correctly
- [ ] Large exports (>1000 pages) work
- [ ] Export respects site restrictions

### Analytics Tests
- [ ] Search queries logged correctly
- [ ] Dashboard shows accurate stats
- [ ] Failed searches tracked
- [ ] Charts render correctly

## Success Metrics

- **API**: 100% endpoint coverage, <100ms response time
- **Rate Limiting**: 99.9% accuracy
- **Exports**: Support up to 10,000 pages
- **Analytics**: Real-time updates within 5 minutes
- **Configuration**: Preview accurate 95%+ of time
- **Auto-reindex**: 100% of due sites re-indexed

## Handoff to Phase 5

Phase 5 will add:
- Horizontal scaling with Kubernetes
- Advanced monitoring and alerting
- Backup and disaster recovery
- Performance optimization
- CDN integration

## Deliverables

- [ ] Site configuration system
- [ ] API key management
- [ ] REST API v1 (all endpoints)
- [ ] Rate limiting
- [ ] Export functionality (JSON/CSV/MD)
- [ ] Analytics dashboard
- [ ] Scheduled re-indexing
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Configuration UI
- [ ] Documentation (this file)

## Definition of Done

Phase 4 is complete when:
1. API keys can be created, used, and revoked
2. All v1 endpoints documented and working
3. Rate limiting prevents abuse
4. Exports work in all formats
5. Analytics dashboard shows real data
6. Auto-reindex runs on schedule
7. Configuration UI allows selector customization
8. API documentation published
9. All tests passing
10. Documentation complete
