"""
FastAPI application entry point with PostgreSQL + Meilisearch support
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException, status, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional, List
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update as sql_update
from datetime import datetime
import asyncio
import json
import redis.asyncio as aioredis

from app.config import get_settings
from app.db import get_db, init_db as async_init_db
from app.models import Site, Page
from app.scraper import WebParser, ScrapingError
from app.meilisearch_engine import MeiliSearchEngine
from app.middleware import SubdomainMiddleware

# Legacy imports for SQLite fallback
from app.database import (
    init_db as sqlite_init_db,
    create_site as sqlite_create_site,
    get_site as sqlite_get_site,
    get_site_by_domain as sqlite_get_site_by_domain,
    update_site_status as sqlite_update_site_status,
    create_page as sqlite_create_page,
    get_all_sites as sqlite_get_all_sites
)
from app.search import SearchEngine as SQLiteSearchEngine


# Get settings
settings = get_settings()

# Determine which backend to use
USE_POSTGRES = settings.database_url.startswith("postgresql")
USE_MEILISEARCH = True  # Will check health on startup


async def check_meilisearch_health() -> bool:
    """Check if Meilisearch is available"""
    try:
        engine = MeiliSearchEngine()
        return engine.health_check()
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global USE_MEILISEARCH
    
    # Startup: initialize database
    if USE_POSTGRES:
        await async_init_db()
        print("✓ PostgreSQL database initialized")
        
        # Check Meilisearch availability
        USE_MEILISEARCH = await check_meilisearch_health()
        if USE_MEILISEARCH:
            print("✓ Meilisearch is available")
        else:
            print("⚠ Meilisearch is not available, search will be limited")
    else:
        # SQLite fallback
        sqlite_init_db(settings.database_url.replace("sqlite:///", ""))
        print("✓ SQLite database initialized (fallback mode)")
        USE_MEILISEARCH = False
    
    yield
    
    # Shutdown: cleanup if needed


# Initialize FastAPI app
app = FastAPI(
    title="Site Search Platform",
    description="A hosted service that creates searchable indexes of any website",
    version="0.2.0",
    lifespan=lifespan
)

# Add subdomain middleware if base_domain is configured
if settings.base_domain:
    app.add_middleware(
        SubdomainMiddleware,
        base_domain=settings.base_domain
    )

# Setup templates
templates = Jinja2Templates(directory="app/templates")


# Pydantic models for API
class ScrapeRequest(BaseModel):
    """Request model for POST /api/scrape"""
    url: HttpUrl
    crawl: bool = True
    max_depth: int = Field(default=2, ge=1, le=5)
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        """Ensure URL is valid and has a scheme"""
        url_str = str(v)
        parsed = urlparse(url_str)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL: must include scheme and domain")
        return v


class SiteResponse(BaseModel):
    """Response model for site details"""
    id: int
    url: str
    domain: str
    status: str
    page_count: int
    last_scraped: Optional[str]
    created_at: str


class SearchResult(BaseModel):
    """Single search result"""
    id: str
    url: str
    title: str
    snippet: str
    rank: float


class SearchResponse(BaseModel):
    """Response model for search results"""
    query: str
    total_results: int
    results: List[SearchResult]
    processing_time_ms: int = 0


class SystemStatus(BaseModel):
    """System status response"""
    status: str
    database: str
    search_engine: str
    web_parser: str
    total_sites: int
    total_pages: int


# Helper functions for async database operations

async def get_or_create_site_async(url: str, domain: str, db: AsyncSession) -> Site:
    """Get existing site or create new one"""
    # Check if site exists
    result = await db.execute(
        select(Site).where(Site.domain == domain)
    )
    site = result.scalar_one_or_none()
    
    if site:
        return site
    
    # Create new site
    site = Site(
        url=url,
        domain=domain,
        status="pending",
        page_count=0
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


async def update_site_status_async(
    site_id: int,
    status_value: str,
    db: AsyncSession,
    page_count: Optional[int] = None
):
    """Update site status in async database"""
    values_to_update: dict = {"status": status_value}
    if page_count is not None:
        values_to_update["page_count"] = page_count
    if status_value == "completed":
        values_to_update["last_scraped"] = datetime.utcnow()
    
    await db.execute(
        sql_update(Site)
        .where(Site.id == site_id)
        .values(**values_to_update)
    )
    await db.commit()
    
    # Return the updated site
    result = await db.execute(select(Site).where(Site.id == site_id))
    return result.scalar_one()


async def create_page_async(
    site_id: int,
    url: str,
    title: str,
    content: str,
    db: AsyncSession
) -> Page:
    """Create a page in async database"""
    page = Page(
        site_id=site_id,
        url=url,
        title=title,
        content=content,
        page_metadata={}
    )
    db.add(page)
    await db.commit()
    await db.refresh(page)
    return page


# API Endpoints

@app.post("/api/scrape", status_code=status.HTTP_202_ACCEPTED)
async def scrape_endpoint(scrape_req: ScrapeRequest):
    """
    Trigger a scrape job for a website
    
    Returns 202 Accepted with site details
    """
    url_str = str(scrape_req.url)
    parsed = urlparse(url_str)
    domain = parsed.netloc
    
    try:
        if USE_POSTGRES:
            # PostgreSQL + async - get db session manually
            async for db in get_db():
                try:
                    site = await get_or_create_site_async(url_str, domain, db)
                    site_id = site.id
                    
                    # Update status to scraping
                    await update_site_status_async(site_id, 'scraping', db)
                    
                    # Start scraping
                    try:
                        parser = WebParser(settings.web_parser_path)
                        pages = parser.scrape(url_str, crawl=scrape_req.crawl, max_depth=scrape_req.max_depth)
                        
                        # Store pages in database
                        page_objects = []
                        for page in pages:
                            page_obj = await create_page_async(
                                site_id=site_id,
                                url=page.get('url', ''),
                                title=page.get('title', ''),
                                content=page.get('content', ''),
                                db=db
                            )
                            page_objects.append(page_obj)
                        
                        # Update site status to completed
                        await update_site_status_async(site_id, 'completed', db, page_count=len(pages))
                        
                        # Index in Meilisearch if available
                        if USE_MEILISEARCH:
                            try:
                                meili = MeiliSearchEngine()
                                pages_to_index = [
                                    {
                                        'id': p.id,
                                        'site_id': p.site_id,
                                        'url': p.url,
                                        'title': p.title,
                                        'content': p.content,
                                        'metadata': p.page_metadata,
                                        'indexed_at': p.indexed_at.isoformat() if p.indexed_at else None
                                    }
                                    for p in page_objects
                                ]
                                await meili.index_pages(pages_to_index)
                            except Exception as e:
                                print(f"Warning: Failed to index in Meilisearch: {e}")
                        
                        return {
                            "site_id": site_id,
                            "url": url_str,
                            "status": "completed",
                            "message": f"Successfully scraped {len(pages)} pages"
                        }
                        
                    except (ScrapingError, TimeoutError, ValueError) as e:
                        # Update site status to failed
                        await update_site_status_async(site_id, 'failed', db)
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Scraping failed: {str(e)}"
                        )
                finally:
                    break  # Only use first db session
        else:
            # SQLite fallback
            db_path = settings.database_url.replace("sqlite:///", "")
            existing_site = sqlite_get_site_by_domain(domain, db_path)
            
            if existing_site:
                site_id = existing_site['id']
                sqlite_update_site_status(site_id, 'scraping', db_path=db_path)
            else:
                site_id = sqlite_create_site(url_str, domain, db_path)
                sqlite_update_site_status(site_id, 'scraping', db_path=db_path)
            
            try:
                parser = WebParser(settings.web_parser_path)
                pages = parser.scrape(url_str, crawl=scrape_req.crawl, max_depth=scrape_req.max_depth)
                
                for page in pages:
                    sqlite_create_page(
                        site_id=site_id,
                        url=page.get('url', ''),
                        title=page.get('title', ''),
                        content=page.get('content', ''),
                        db_path=db_path
                    )
                
                sqlite_update_site_status(site_id, 'completed', page_count=len(pages), db_path=db_path)
                
                return {
                    "site_id": site_id,
                    "url": url_str,
                    "status": "completed",
                    "message": f"Successfully scraped {len(pages)} pages"
                }
                
            except (ScrapingError, TimeoutError, ValueError) as e:
                sqlite_update_site_status(site_id, 'failed', db_path=db_path)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Scraping failed: {str(e)}"
                )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@app.get("/api/search")
async def search_endpoint(
    q: str = Query(..., min_length=1, description="Search query"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Search indexed pages
    
    Query parameters:
    - q: Search query (required)
    - site_id: Filter by site ID (optional)
    - limit: Max results (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' is required"
        )
    
    try:
        if USE_POSTGRES and USE_MEILISEARCH:
            # Use Meilisearch for search
            meili = MeiliSearchEngine()
            results = await meili.search(q, site_id=site_id, limit=limit, offset=offset)
            
            return SearchResponse(
                query=results['query'],
                total_results=results['total_hits'],
                processing_time_ms=results['processing_time_ms'],
                results=[
                    SearchResult(
                        id=r['id'],
                        url=r['url'],
                        title=r['title'],
                        snippet=r['snippet'],
                        rank=r['rank']
                    )
                    for r in results['hits']
                ]
            )
        else:
            # Use SQLite FTS5 fallback
            db_path = settings.database_url.replace("sqlite:///", "")
            search_engine = SQLiteSearchEngine(db_path)
            results = search_engine.search(q, site_id=site_id, limit=limit)
            
            return SearchResponse(
                query=q,
                total_results=len(results),
                results=[
                    SearchResult(
                        id=str(r['id']),
                        url=r['url'],
                        title=r['title'],
                        snippet=r['snippet'],
                        rank=r['rank']
                    )
                    for r in results
                ]
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@app.get("/api/search/partial", response_class=HTMLResponse)
async def search_partial_endpoint(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Search indexed pages and return HTML partial for HTMX
    
    Query parameters:
    - q: Search query (optional, empty returns no results message)
    - site_id: Filter by site ID (optional)
    - limit: Max results (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    """
    # If no query provided, return empty state
    if not q or not q.strip():
        return templates.TemplateResponse(
            request=request,
            name="partials/search_results.html",
            context={
                "query": "",
                "results": [],
                "total_results": 0
            }
        )
    
    try:
        if USE_POSTGRES and USE_MEILISEARCH:
            # Use Meilisearch for search
            meili = MeiliSearchEngine()
            results = await meili.search(q, site_id=site_id, limit=limit, offset=offset)
            
            return templates.TemplateResponse(
                request=request,
                name="partials/search_results.html",
                context={
                    "query": q,
                    "results": results['hits'],
                    "total_results": results['total_hits'],
                    "processing_time_ms": results['processing_time_ms']
                }
            )
        else:
            # Use SQLite FTS5 fallback
            db_path = settings.database_url.replace("sqlite:///", "")
            search_engine = SQLiteSearchEngine(db_path)
            results = search_engine.search(q, site_id=site_id, limit=limit)
            
            return templates.TemplateResponse(
                request=request,
                name="partials/search_results.html",
                context={
                    "query": q,
                    "results": results,
                    "total_results": len(results)
                }
            )
    
    except Exception as e:
        # Return error message as HTML partial
        return templates.TemplateResponse(
            request=request,
            name="partials/search_results.html",
            context={
                "query": q,
                "results": [],
                "total_results": 0,
                "error": str(e)
            }
        )



@app.get("/api/sites/{site_id}")
async def get_site_endpoint(site_id: int):
    """
    Get site details by ID
    """
    try:
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    result = await db.execute(
                        select(Site).where(Site.id == site_id)
                    )
                    site = result.scalar_one_or_none()
                    
                    if not site:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Site {site_id} not found"
                        )
                    
                    return SiteResponse(
                        id=site.id,
                        url=site.url,
                        domain=site.domain,
                        status=site.status,
                        page_count=site.page_count,
                        last_scraped=site.last_scraped.isoformat() if site.last_scraped else None,
                        created_at=site.created_at.isoformat()
                    )
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            site = sqlite_get_site(site_id, db_path)
            
            if not site:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Site {site_id} not found"
                )
            
            return SiteResponse(
                id=site['id'],
                url=site['url'],
                domain=site['domain'],
                status=site['status'],
                page_count=site['page_count'],
                last_scraped=site['last_scraped'],
                created_at=site['created_at']
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving site: {str(e)}"
        )


@app.get("/api/status")
async def status_endpoint():
    """
    Get system status
    """
    try:
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    # Get site count
                    result = await db.execute(select(func.count(Site.id)))
                    total_sites = result.scalar()
                    
                    # Get page count
                    result = await db.execute(select(func.count(Page.id)))
                    total_pages = result.scalar()
                    
                    # Check web parser
                    from pathlib import Path
                    parser_exists = Path(settings.web_parser_path).exists()
                    
                    return SystemStatus(
                        status="ok",
                        database="postgresql",
                        search_engine="meilisearch" if USE_MEILISEARCH else "none",
                        web_parser="ok" if parser_exists else "not_found",
                        total_sites=total_sites or 0,
                        total_pages=total_pages or 0
                    )
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            sites = sqlite_get_all_sites(db_path)
            total_sites = len(sites)
            
            from app.database import get_db_connection
            conn = get_db_connection(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pages")
            total_pages = cursor.fetchone()[0]
            conn.close()
            
            from pathlib import Path
            parser_exists = Path(settings.web_parser_path).exists()
            
            return SystemStatus(
                status="ok",
                database="sqlite",
                search_engine="sqlite_fts5",
                web_parser="ok" if parser_exists else "not_found",
                total_sites=total_sites,
                total_pages=total_pages
            )
    
    except Exception as e:
        return SystemStatus(
            status="error",
            database=f"error: {str(e)}",
            search_engine="unknown",
            web_parser="unknown",
            total_sites=0,
            total_pages=0
        )


@app.get("/api/sites/{site_id}/progress/stream")
async def progress_stream(site_id: int):
    """
    Server-Sent Events (SSE) endpoint for real-time scraping progress.
    
    Polls Redis for progress data every 1 second and yields SSE events.
    Closes stream when scraping completes or fails.
    
    Args:
        site_id: Database ID of the site being scraped
        
    Returns:
        StreamingResponse with text/event-stream content type
    """
    async def event_generator():
        """Generate SSE events from Redis progress data."""
        # Connect to Redis
        redis_client = await aioredis.from_url("redis://localhost:6379/0")
        progress_key = f"scrape_progress:{site_id}"
        
        try:
            while True:
                # Get progress data from Redis hash
                progress_data = await redis_client.hgetall(progress_key)
                
                if progress_data:
                    # Decode bytes to strings
                    progress = {
                        k.decode('utf-8'): v.decode('utf-8') 
                        for k, v in progress_data.items()
                    }
                    
                    # Build event data
                    event_data = {
                        "pages_found": int(progress.get("pages_found", 0)),
                        "current_url": progress.get("current_url", ""),
                        "status": progress.get("status", "scraping"),
                        "updated_at": progress.get("updated_at", "")
                    }
                    
                    # Check if scraping is complete or failed
                    status_value = progress.get("status", "scraping")
                    if status_value in ["completed", "failed"]:
                        event_data["done"] = True
                        # Send final event
                        yield f"data: {json.dumps(event_data)}\n\n"
                        break
                    
                    # Send progress event
                    yield f"data: {json.dumps(event_data)}\n\n"
                else:
                    # No progress data yet, send initial event
                    yield f"data: {json.dumps({'status': 'waiting', 'pages_found': 0})}\n\n"
                
                # Poll every 1 second
                await asyncio.sleep(1)
                
        except Exception as e:
            # Send error event
            error_data = {
                "error": str(e),
                "status": "error",
                "done": True
            }
            yield f"data: {json.dumps(error_data)}\n\n"
        finally:
            # Close Redis connection
            await redis_client.close()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


# Template Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Root endpoint with subdomain-based routing.
    
    If subdomain present: Look up site by domain and route based on status:
        - Site not found: Show setup/scrape page
        - Site status=scraping: Show progress page
        - Site status=completed: Show search page
        - Site status=failed/pending: Show status page
    
    If no subdomain: Show landing page with site list
    """
    try:
        # Check if this is a subdomain request
        is_subdomain = getattr(request.state, 'is_subdomain', False)
        subdomain = getattr(request.state, 'subdomain', None)
        
        if is_subdomain and subdomain:
            # Subdomain routing: look up site by domain (subdomain is the domain)
            if USE_POSTGRES:
                async for db in get_db():
                    try:
                        # Look up site by domain matching the subdomain
                        result = await db.execute(
                            select(Site).where(Site.domain == subdomain)
                        )
                        site_orm = result.scalar_one_or_none()
                        
                        if not site_orm:
                            # Site not found - show setup/scrape page
                            return templates.TemplateResponse(
                                request=request,
                                name="status.html",
                                context={
                                    "domain": subdomain,
                                    "site": None,
                                    "url": f"https://{subdomain}"
                                }
                            )
                        
                        # Convert to dict for template
                        site = {
                            'id': site_orm.id,
                            'url': site_orm.url,
                            'domain': site_orm.domain,
                            'status': site_orm.status,
                            'page_count': site_orm.page_count,
                            'last_scraped': site_orm.last_scraped.isoformat() if site_orm.last_scraped else None,
                            'created_at': site_orm.created_at.isoformat()
                        }
                        
                        # Route based on site status
                        if site['status'] == 'scraping':
                            # Show progress page
                            return templates.TemplateResponse(
                                request=request,
                                name="status.html",
                                context={
                                    "domain": subdomain,
                                    "site": site
                                }
                            )
                        elif site['status'] == 'completed':
                            # Show search page
                            return templates.TemplateResponse(
                                request=request,
                                name="search.html",
                                context={
                                    "site": site,
                                    "query": "",
                                    "results": []
                                }
                            )
                        else:
                            # Show status page for pending/failed
                            return templates.TemplateResponse(
                                request=request,
                                name="status.html",
                                context={
                                    "domain": subdomain,
                                    "site": site
                                }
                            )
                    finally:
                        break
            else:
                # SQLite fallback
                db_path = settings.database_url.replace("sqlite:///", "")
                site = sqlite_get_site_by_domain(subdomain, db_path)
                
                if not site:
                    # Site not found - show setup/scrape page
                    return templates.TemplateResponse(
                        request=request,
                        name="status.html",
                        context={
                            "domain": subdomain,
                            "site": None,
                            "url": f"https://{subdomain}"
                        }
                    )
                
                # Route based on site status
                if site['status'] == 'scraping':
                    # Show progress page
                    return templates.TemplateResponse(
                        request=request,
                        name="status.html",
                        context={
                            "domain": subdomain,
                            "site": site
                        }
                    )
                elif site['status'] == 'completed':
                    # Show search page
                    return templates.TemplateResponse(
                        request=request,
                        name="search.html",
                        context={
                            "site": site,
                            "query": "",
                            "results": []
                        }
                    )
                else:
                    # Show status page for pending/failed
                    return templates.TemplateResponse(
                        request=request,
                        name="status.html",
                        context={
                            "domain": subdomain,
                            "site": site
                        }
                    )
        
        # No subdomain - show landing page with site list
        sites = []
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    result = await db.execute(
                        select(Site).order_by(Site.created_at.desc())
                    )
                    sites_orm = result.scalars().all()
                    
                    # Convert to dict format for template
                    sites = [
                        {
                            'id': s.id,
                            'url': s.url,
                            'domain': s.domain,
                            'status': s.status,
                            'page_count': s.page_count,
                            'last_scraped': s.last_scraped.isoformat() if s.last_scraped else None,
                            'created_at': s.created_at.isoformat()
                        }
                        for s in sites_orm
                    ]
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            sites = sqlite_get_all_sites(db_path)
        
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"sites": sites}
        )
    except Exception as e:
        print(f"Error in index: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback to landing page on error
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"sites": [], "error": str(e)}
        )


@app.post("/scrape", response_class=HTMLResponse)
async def scrape_form(request: Request, url: str = Form(...)):
    """
    Handle scrape form submission from web UI
    """
    try:
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError("Invalid URL")
        
        domain = parsed.netloc
        
        # Redirect to status page for this domain
        return RedirectResponse(
            url=f"/site/{domain}/status",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "sites": [],
                "error": f"Invalid URL: {str(e)}"
            }
        )


@app.get("/site/{domain}/search", response_class=HTMLResponse)
async def site_search_page(
    request: Request,
    domain: str,
    q: Optional[str] = None
):
    """
    Search page for a specific site
    """
    try:
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    # Get site by domain
                    result = await db.execute(
                        select(Site).where(Site.domain == domain)
                    )
                    site_orm = result.scalar_one_or_none()
                    
                    if not site_orm:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Site {domain} not found"
                        )
                    
                    site = {
                        'id': site_orm.id,
                        'url': site_orm.url,
                        'domain': site_orm.domain,
                        'status': site_orm.status,
                        'page_count': site_orm.page_count
                    }
                    
                    results = []
                    if q and q.strip() and USE_MEILISEARCH:
                        meili = MeiliSearchEngine()
                        search_results = await meili.search(q, site_id=site_orm.id, limit=20)
                        results = search_results['hits']
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            site = sqlite_get_site_by_domain(domain, db_path)
            
            if not site:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Site {domain} not found"
                )
            
            results = []
            if q and q.strip():
                search_engine = SQLiteSearchEngine(db_path)
                results = search_engine.search(q, site_id=site['id'], limit=20)
        
        return templates.TemplateResponse(
            request=request,
            name="search.html",
            context={
                "site": site,
                "query": q or "",
                "results": results
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in site search page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading search page: {str(e)}"
        )


@app.get("/site/{domain}/status", response_class=HTMLResponse)
async def site_status_page(request: Request, domain: str):
    """
    Status page for a site (shows scrape progress/completion)
    """
    try:
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    # Get site by domain
                    result = await db.execute(
                        select(Site).where(Site.domain == domain)
                    )
                    site_orm = result.scalar_one_or_none()
                    
                    if not site_orm:
                        # Site doesn't exist, show setup form
                        return templates.TemplateResponse(
                            request=request,
                            name="status.html",
                            context={
                                "domain": domain,
                                "site": None,
                                "url": f"https://{domain}"
                            }
                        )
                    
                    site = {
                        'id': site_orm.id,
                        'url': site_orm.url,
                        'domain': site_orm.domain,
                        'status': site_orm.status,
                        'page_count': site_orm.page_count,
                        'last_scraped': site_orm.last_scraped.isoformat() if site_orm.last_scraped else None,
                        'created_at': site_orm.created_at.isoformat()
                    }
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            site = sqlite_get_site_by_domain(domain, db_path)
            
            if not site:
                # Site doesn't exist, show setup form
                return templates.TemplateResponse(
                    request=request,
                    name="status.html",
                    context={
                        "domain": domain,
                        "site": None,
                        "url": f"https://{domain}"
                    }
                )
        
        return templates.TemplateResponse(
            request=request,
            name="status.html",
            context={
                "domain": domain,
                "site": site
            }
        )
    except Exception as e:
        print(f"Error in site status page: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading status page: {str(e)}"
        )


@app.post("/site/{domain}/scrape")
async def trigger_site_scrape(domain: str, url: str = Form(...)):
    """
    Trigger scraping for a site from the status page
    """
    try:
        if USE_POSTGRES:
            async for db in get_db():
                try:
                    # Get or create site
                    site = await get_or_create_site_async(url, domain, db)
                    site_id = site.id
                    
                    # Update status to scraping
                    await update_site_status_async(site_id, 'scraping', db)
                    
                    # Start scraping
                    try:
                        parser = WebParser(settings.web_parser_path)
                        pages = parser.scrape(url, crawl=True, max_depth=2)
                        
                        # Store pages
                        page_objects = []
                        for page in pages:
                            page_obj = await create_page_async(
                                site_id=site_id,
                                url=page.get('url', ''),
                                title=page.get('title', ''),
                                content=page.get('content', ''),
                                db=db
                            )
                            page_objects.append(page_obj)
                        
                        # Update status
                        await update_site_status_async(site_id, 'completed', db, page_count=len(pages))
                        
                        # Index in Meilisearch if available
                        if USE_MEILISEARCH:
                            try:
                                meili = MeiliSearchEngine()
                                pages_to_index = [
                                    {
                                        'id': p.id,
                                        'site_id': p.site_id,
                                        'url': p.url,
                                        'title': p.title,
                                        'content': p.content,
                                        'metadata': p.page_metadata,
                                        'indexed_at': p.indexed_at.isoformat() if p.indexed_at else None
                                    }
                                    for p in page_objects
                                ]
                                await meili.index_pages(pages_to_index)
                            except Exception as e:
                                print(f"Warning: Failed to index in Meilisearch: {e}")
                        
                    except Exception as e:
                        await update_site_status_async(site_id, 'failed', db)
                        raise
                finally:
                    break
        else:
            db_path = settings.database_url.replace("sqlite:///", "")
            existing_site = sqlite_get_site_by_domain(domain, db_path)
            
            if existing_site:
                site_id = existing_site['id']
                sqlite_update_site_status(site_id, 'scraping', db_path=db_path)
            else:
                site_id = sqlite_create_site(url, domain, db_path)
                sqlite_update_site_status(site_id, 'scraping', db_path=db_path)
            
            try:
                parser = WebParser(settings.web_parser_path)
                pages = parser.scrape(url, crawl=True, max_depth=2)
                
                for page in pages:
                    sqlite_create_page(
                        site_id=site_id,
                        url=page.get('url', ''),
                        title=page.get('title', ''),
                        content=page.get('content', ''),
                        db_path=db_path
                    )
                
                sqlite_update_site_status(site_id, 'completed', page_count=len(pages), db_path=db_path)
                
            except Exception as e:
                sqlite_update_site_status(site_id, 'failed', db_path=db_path)
                raise
        
        # Redirect back to status page
        return RedirectResponse(
            url=f"/site/{domain}/status",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraping failed: {str(e)}"
        )
