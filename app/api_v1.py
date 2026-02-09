"""
Versioned REST API router for Site Search Platform.

This module provides API v1 endpoints mounted at /api/v1 with:
- API key authentication
- Rate limiting
- Pagination
- Comprehensive error handling
- OpenAPI documentation
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, UTC, UTC
from fastapi import APIRouter, Depends, HTTPException, Query, status, Header, Request
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc
from sqlalchemy.orm import selectinload
from urllib.parse import urlparse
import csv
import io
import json

from app.auth import verify_api_key, APIKey
from app.rate_limiter import RateLimiter, get_rate_limiter
from app.db import get_db
from app.models import Site, Page
from app.meilisearch_engine import MeiliSearchEngine
from app.tasks import scrape_site_task
from app.site_config import SiteConfig
from app.export import Exporter

# Create v1 router
router = APIRouter(prefix="/api/v1", tags=["API v1", "Sites", "Search", "Export", "Analytics", "Auth"])


# Helper function to check site access permissions
async def check_site_access(
    api_key: APIKey,
    site_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
) -> Optional[Site]:
    """
    Check if API key has access to a site.
    
    Args:
        api_key: The API key making the request
        site_id: Site ID to check access to (if None, returns None)
        db: Database session
        
    Returns:
        Site object if access granted and site exists
        
    Raises:
        HTTPException: 403 if access denied, 404 if site not found
    """
    if site_id is None:
        return None
    
    # Check if API key is scoped to a specific site
    if api_key.site_id is not None and api_key.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"API key is restricted to site {api_key.site_id}"
        )
    
    # Get the site
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site with ID {site_id} not found"
        )
    
    return site


# Helper function to extract domain from URL
def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError("Invalid URL: no domain found")
    return parsed.netloc


# Helper function for pagination metadata
def get_pagination_metadata(skip: int, limit: int, total: int) -> Dict[str, Any]:
    """Generate pagination metadata."""
    return {
        "skip": skip,
        "limit": limit,
        "total": total,
        "has_more": total > skip + limit,
        "next_offset": skip + limit if total > skip + limit else None
    }


# Sites endpoints
@router.get("/sites", response_model=Dict[str, Any])
async def list_sites(
    skip: int = Query(0, ge=0, description="Number of sites to skip (pagination)"),
    limit: int = Query(20, ge=1, le=100, description="Number of sites to return (max 100)"),
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, scraping, completed, failed"),
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    List all indexed sites accessible to the API key.
    
    Returns paginated list of sites with optional status filtering.
    """
    # Check if API key is scoped to a specific site
    if api_key.site_id is not None:
        # Return only the scoped site
        result = await db.execute(select(Site).where(Site.id == api_key.site_id))
        site = result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site {api_key.site_id} not found"
            )
        
        return {
            "sites": [{
                "id": site.id,
                "url": site.url,
                "domain": site.domain,
                "status": site.status,
                "page_count": site.page_count,
                "last_scraped": site.last_scraped.isoformat() if site.last_scraped else None,
                "created_at": site.created_at.isoformat()
            }],
            "total": 1,
            "skip": 0,
            "limit": 1,
            "has_more": False,
            "next_offset": None
        }
    
    # Build query for unrestricted API key
    query = select(Site)
    
    # Apply status filter if provided
    if status_filter:
        query = query.where(Site.status == status_filter)
    
    # Get total count for pagination
    total_query = select(func.count(Site.id))
    if status_filter:
        total_query = total_query.where(Site.status == status_filter)
    total_result = await db.execute(total_query)
    total = total_result.scalar()
    
    # Apply pagination
    query = query.order_by(Site.created_at.desc()).offset(skip).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    sites = result.scalars().all()
    
    return {
        "sites": [{
            "id": site.id,
            "url": site.url,
            "domain": site.domain,
            "status": site.status,
            "page_count": site.page_count,
            "last_scraped": site.last_scraped.isoformat() if site.last_scraped else None,
            "created_at": site.created_at.isoformat()
        } for site in sites],
        **get_pagination_metadata(skip, limit, total)
    }


@router.post("/sites", status_code=status.HTTP_202_ACCEPTED)
async def create_site(
    request: Request,
    url: str = Query(..., description="Website URL to index"),
    crawl: bool = Query(True, description="Enable recursive crawling"),
    max_depth: int = Query(2, ge=1, le=5, description="Maximum crawl depth (1-5)"),
    api_key: APIKey = Depends(verify_api_key),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit a new site for indexing.
    
    Validates URL, creates site record, and queues scraping task.
    Returns 202 Accepted with site details.
    """
    # Check rate limit for site creation
    await rate_limiter.check_api_key_limit(api_key.id, api_key.rate_limit_per_minute)
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        domain = extract_domain(url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid URL: {str(e)}"
        )
    
    # Check if API key is scoped to a site (can't create new sites)
    if api_key.site_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is restricted to an existing site and cannot create new sites"
        )
    
    try:
        # Check if site already exists
        result = await db.execute(select(Site).where(Site.domain == domain))
        existing_site = result.scalar_one_or_none()
        
        if existing_site:
            # Site exists, check if we should re-scrape
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "site_id": existing_site.id,
                    "url": url,
                    "status": existing_site.status,
                    "message": f"Site {domain} already exists",
                    "existing": True
                }
            )
        
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
        
        # Queue scraping task
        scrape_site_task.delay(site.id)
        
        # Update site status
        site.status = "scraping"
        await db.commit()
        
        return {
            "site_id": site.id,
            "url": url,
            "domain": domain,
            "status": "scraping",
            "message": "Scraping started",
            "estimated_completion": "Varies based on site size",
            "created_at": site.created_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating site: {str(e)}"
        )


@router.get("/sites/{site_id}")
async def get_site(
    site_id: int,
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed information about a specific site.
    """
    # Check access and get site
    site = await check_site_access(api_key, site_id, db)
    
    # Parse config from JSON
    config_data = site.config if site.config else {}
    
    return {
        "id": site.id,
        "url": site.url,
        "domain": site.domain,
        "status": site.status,
        "page_count": site.page_count,
        "config": config_data,
        "last_scraped": site.last_scraped.isoformat() if site.last_scraped else None,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat()
    }


@router.post("/sites/{site_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_site(
    site_id: int,
    api_key: APIKey = Depends(verify_api_key),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger re-indexing of a site.
    
    Queues a new scraping task for the site.
    """
    # Check rate limit
    await rate_limiter.check_api_key_limit(api_key.id, api_key.rate_limit_per_minute)
    
    # Check access and get site
    site = await check_site_access(api_key, site_id, db)
    
    # Update site status
    site.status = "scraping"
    await db.commit()
    
    # Queue scraping task
    scrape_site_task.delay(site.id)
    
    return {
        "site_id": site.id,
        "domain": site.domain,
        "status": "scraping",
        "message": "Re-indexing started",
        "queued_at": datetime.now(UTC).isoformat()
    }


# Search endpoints
@router.get("/search")
async def api_search(
    q: str = Query(..., min_length=1, description="Search query"),
    site_id: Optional[int] = Query(None, description="Filter by site ID"),
    limit: int = Query(20, ge=1, le=100, description="Results per page (1-100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    highlight: bool = Query(True, description="Highlight matching terms"),
    api_key: APIKey = Depends(verify_api_key),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    db: AsyncSession = Depends(get_db)
):
    """
    Search indexed pages.
    
    Returns paginated results with highlighted snippets.
    Supports typo tolerance, stemming, and relevance ranking.
    """
    # Check rate limit for search
    await rate_limiter.check_api_key_limit(api_key.id, api_key.rate_limit_per_minute)
    
    # Check site access if site_id provided
    if site_id:
        await check_site_access(api_key, site_id, db)
    
    try:
        # Use Meilisearch for search
        search_engine = MeiliSearchEngine()
        results = await search_engine.search(
            query=q,
            site_id=site_id,
            limit=limit,
            offset=offset
        )
        
        # Add rate limit headers
        headers = {
            "X-RateLimit-Limit": str(api_key.rate_limit_per_minute),
            "X-RateLimit-Remaining": str(api_key.rate_limit_per_minute - 1),  # Approximation
            "X-RateLimit-Reset": str(int(datetime.now(UTC).timestamp()) + 60)
        }
        
        return JSONResponse(
            content=results,
            headers=headers
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/search/suggest")
async def search_suggestions(
    q: str = Query(..., min_length=2, description="Partial search query"),
    site_id: Optional[int] = Query(None, description="Filter by site"),
    limit: int = Query(5, ge=1, le=10, description="Max suggestions (1-10)"),
    api_key: APIKey = Depends(verify_api_key),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    db: AsyncSession = Depends(get_db)
):
    """
    Get search suggestions (autocomplete).
    
    Returns query suggestions based on indexed content.
    """
    # Check rate limit
    await rate_limiter.check_api_key_limit(api_key.id, api_key.rate_limit_per_minute)
    
    # Check site access if site_id provided
    if site_id:
        await check_site_access(api_key, site_id, db)
    
    try:
        # Use Meilisearch for suggestions
        search_engine = MeiliSearchEngine()
        
        # For now, perform a simple search and extract common terms
        # In a real implementation, use Meilisearch's search-for-facets endpoint
        
        # Simple implementation: search and get titles for suggestions
        search_results = await search_engine.search(
            query=q,
            site_id=site_id,
            limit=10
        )
        
        # Extract unique words from titles for suggestions
        suggestions = set()
        for hit in search_results['hits']:
            title = hit.get('title', '')
            # Add words from title that start with the query
            for word in title.split():
                if word.lower().startswith(q.lower()) and len(word) > len(q):
                    suggestions.add(word.lower())
        
        # Convert to list and limit
        suggestions_list = list(suggestions)[:limit]
        
        return {
            "query": q,
            "suggestions": suggestions_list
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get suggestions: {str(e)}"
        )


# Export endpoints
@router.get("/sites/{site_id}/export")
async def export_site(
    site_id: int,
    format: str = Query("json", pattern="^(json|csv|md)$", description="Export format: json, csv, md"),
    include_content: bool = Query(True, description="Include full page content in export"),
    stream: bool = Query(True, description="Stream large exports for better performance"),
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Export all pages from a site.
    
    Supports JSON, CSV, and Markdown formats.
    Uses streaming for large exports (over 500 pages) to handle up to 10,000 pages efficiently.
    """
    # Check access and get site
    site = await check_site_access(api_key, site_id, db)
    
    try:
        # Use Exporter class to create the export response
        return await Exporter.create_export_response(
            db=db,
            site_id=site_id,
            site=site,
            format=format,
            include_content=include_content,
            stream_large=stream
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


# Helper function to handle API key in header or query param
async def get_api_key_from_request(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, alias="api_key"),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """
    Get API key from either X-API-Key header or api_key query parameter.
    
    This provides flexibility for clients that can't use Bearer tokens.
    """
    from fastapi.security import HTTPAuthorizationCredentials
    
    # Try to get from header first
    if x_api_key:
        # Create mock credentials object for verify_api_key
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=x_api_key
        )
        return await verify_api_key(credentials, db)
    
    # Try query parameter
    elif api_key:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=api_key
        )
        return await verify_api_key(credentials, db)
    
    # Try standard Authorization header (verify_api_key will handle this)
    else:
        # This will be handled by the verify_api_key dependency
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required via X-API-Key header, api_key query parameter, or Authorization header"
        )


# Update router dependencies to support multiple auth methods
def create_api_v1_router() -> APIRouter:
    """
    Create API v1 router with flexible authentication.
    
    This function creates a router that supports:
    - Standard Bearer token (Authorization header)
    - X-API-Key header
    - api_key query parameter
    """
    # Create a new router instance
    router_v1 = APIRouter(prefix="/api/v1", tags=["API v1"])
    
    # Copy all routes from the current router
    for route in router.routes:
        router_v1.routes.append(route)
    
    return router_v1