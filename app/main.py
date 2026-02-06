"""
FastAPI application entry point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional, List
from urllib.parse import urlparse
import traceback

from app.config import get_settings
from app.database import (
    init_db,
    create_site,
    get_site,
    get_site_by_domain,
    update_site_status,
    create_page,
    get_all_sites
)
from app.scraper import WebParser, ScrapingError
from app.search import SearchEngine


# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup: initialize database
    init_db(settings.database_url.replace("sqlite:///", ""))
    yield
    # Shutdown: cleanup if needed


# Initialize FastAPI app
app = FastAPI(
    title="Site Search Platform",
    description="A hosted service that creates searchable indexes of any website",
    version="0.1.0",
    lifespan=lifespan
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
    id: int
    url: str
    title: str
    snippet: str
    rank: float


class SearchResponse(BaseModel):
    """Response model for search results"""
    query: str
    total_results: int
    results: List[SearchResult]


class SystemStatus(BaseModel):
    """System status response"""
    status: str
    database: str
    web_parser: str
    total_sites: int
    total_pages: int


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
    
    db_path = settings.database_url.replace("sqlite:///", "")
    
    try:
        # Check if site already exists
        existing_site = get_site_by_domain(domain, db_path)
        
        if existing_site:
            site_id = existing_site['id']
            # Update status to scraping
            update_site_status(site_id, 'scraping', db_path=db_path)
        else:
            # Create new site
            site_id = create_site(url_str, domain, db_path)
            update_site_status(site_id, 'scraping', db_path=db_path)
        
        # Start scraping
        try:
            parser = WebParser(settings.web_parser_path)
            pages = parser.scrape(url_str, crawl=scrape_req.crawl, max_depth=scrape_req.max_depth)
            
            # Store pages in database
            for page in pages:
                create_page(
                    site_id=site_id,
                    url=page.get('url', ''),
                    title=page.get('title', ''),
                    content=page.get('content', ''),
                    db_path=db_path
                )
            
            # Update site status to completed
            update_site_status(site_id, 'completed', page_count=len(pages), db_path=db_path)
            
            return {
                "site_id": site_id,
                "url": url_str,
                "status": "completed",
                "message": f"Successfully scraped {len(pages)} pages"
            }
            
        except (ScrapingError, TimeoutError, ValueError) as e:
            # Update site status to failed
            update_site_status(site_id, 'failed', db_path=db_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Scraping failed: {str(e)}"
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@app.get("/api/search")
async def search_endpoint(
    q: str,
    site_id: Optional[int] = None,
    limit: int = 20
):
    """
    Search indexed pages
    
    Query parameters:
    - q: Search query (required)
    - site_id: Filter by site ID (optional)
    - limit: Max results (default: 20, max: 100)
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' is required"
        )
    
    # Limit max results
    limit = min(limit, 100)
    
    db_path = settings.database_url.replace("sqlite:///", "")
    
    try:
        search_engine = SearchEngine(db_path)
        results = search_engine.search(q, site_id=site_id, limit=limit)
        
        return SearchResponse(
            query=q,
            total_results=len(results),
            results=[
                SearchResult(
                    id=r['id'],
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


@app.get("/api/sites/{site_id}")
async def get_site_endpoint(site_id: int):
    """
    Get site details by ID
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    
    site = get_site(site_id, db_path)
    
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


@app.get("/api/status")
async def status_endpoint():
    """
    Get system status
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    
    try:
        # Check database
        sites = get_all_sites(db_path)
        total_sites = len(sites)
        
        # Count total pages
        from app.database import get_db_connection
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pages")
        total_pages = cursor.fetchone()[0]
        conn.close()
        
        # Check web parser
        from pathlib import Path
        parser_exists = Path(settings.web_parser_path).exists()
        
        return SystemStatus(
            status="ok",
            database="ok",
            web_parser="ok" if parser_exists else "not_found",
            total_sites=total_sites,
            total_pages=total_pages
        )
    
    except Exception as e:
        return SystemStatus(
            status="error",
            database=f"error: {str(e)}",
            web_parser="unknown",
            total_sites=0,
            total_pages=0
        )


# Template Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Landing page with scrape form and site list
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    sites = get_all_sites(db_path)
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"sites": sites}
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
        db_path = settings.database_url.replace("sqlite:///", "")
        sites = get_all_sites(db_path)
        
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "sites": sites,
                "error": f"Invalid URL: {str(e)}"
            }
        )


@app.get("/site/{domain}/search", response_class=HTMLResponse)
async def site_search_page(request: Request, domain: str, q: Optional[str] = None):
    """
    Search page for a specific site
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    
    # Get site by domain
    site = get_site_by_domain(domain, db_path)
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site {domain} not found"
        )
    
    results = []
    if q and q.strip():
        search_engine = SearchEngine(db_path)
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


@app.get("/site/{domain}/status", response_class=HTMLResponse)
async def site_status_page(request: Request, domain: str):
    """
    Status page for a site (shows scrape progress/completion)
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    
    # Get or create site
    site = get_site_by_domain(domain, db_path)
    
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


@app.post("/site/{domain}/scrape")
async def trigger_site_scrape(domain: str, url: str = Form(...)):
    """
    Trigger scraping for a site from the status page
    """
    db_path = settings.database_url.replace("sqlite:///", "")
    
    try:
        # Create or get site
        existing_site = get_site_by_domain(domain, db_path)
        
        if existing_site:
            site_id = existing_site['id']
            update_site_status(site_id, 'scraping', db_path=db_path)
        else:
            site_id = create_site(url, domain, db_path)
            update_site_status(site_id, 'scraping', db_path=db_path)
        
        # Start scraping
        try:
            parser = WebParser(settings.web_parser_path)
            pages = parser.scrape(url, crawl=True, max_depth=2)
            
            # Store pages
            for page in pages:
                create_page(
                    site_id=site_id,
                    url=page.get('url', ''),
                    title=page.get('title', ''),
                    content=page.get('content', ''),
                    db_path=db_path
                )
            
            # Update status
            update_site_status(site_id, 'completed', page_count=len(pages), db_path=db_path)
            
        except Exception as e:
            update_site_status(site_id, 'failed', db_path=db_path)
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
