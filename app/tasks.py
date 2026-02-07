"""
Celery background tasks for scraping websites.

This module contains Celery tasks for asynchronous web scraping,
including progress tracking, database storage, and search indexing.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any
from celery.exceptions import MaxRetriesExceededError
import redis

from app.celery_app import celery_app
from app.db import AsyncSessionLocal
from app.models import Site, Page
from app.scraper import WebParser
from app.meilisearch_engine import MeiliSearchEngine
from sqlalchemy import select


@celery_app.task(bind=True, max_retries=3)
def scrape_site_task(self, site_id: int) -> Dict[str, Any]:
    """
    Celery task to scrape a website in the background.
    
    This task:
    - Scrapes a site using the async web parser
    - Stores pages in PostgreSQL
    - Indexes pages in Meilisearch
    - Tracks progress in Redis (hash with pages_found, current_url, status, updated_at)
    - Implements exponential backoff retry (60s, 120s, 240s)
    - Updates site status to scraping/completed/failed
    
    Args:
        self: Celery task instance (bind=True)
        site_id: Database ID of the site to scrape
        
    Returns:
        Dict with scraping results (site_id, pages_scraped, status)
        
    Raises:
        MaxRetriesExceededError: If all 3 retry attempts fail
    """
    # Run async code in sync Celery task using asyncio.run
    return asyncio.run(_scrape_site_async(self, site_id))


async def _scrape_site_async(task, site_id: int) -> Dict[str, Any]:
    """
    Async implementation of site scraping.
    
    Args:
        task: Celery task instance for state updates
        site_id: Database ID of the site to scrape
        
    Returns:
        Dict with scraping results
    """
    # Initialize Redis for progress tracking
    redis_client = redis.from_url("redis://localhost:6379/0")
    progress_key = f"scrape_progress:{site_id}"
    
    async with AsyncSessionLocal() as db:
        try:
            # Get site details
            result = await db.execute(select(Site).where(Site.id == site_id))
            site = result.scalar_one_or_none()
            
            if not site:
                raise ValueError(f"Site {site_id} not found")
            
            # Update site status to scraping
            site.status = "scraping"
            await db.commit()
            
            # Initialize progress tracking
            page_count = 0
            
            # Update initial progress in Redis
            redis_client.hset(
                progress_key,
                mapping={
                    "pages_found": 0,
                    "current_url": site.url,
                    "status": "scraping",
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            redis_client.expire(progress_key, 3600)  # 1 hour TTL
            
            # Progress callback to update Redis
            def progress_callback(count: int, url: str):
                nonlocal page_count
                page_count = count
                
                # Update task state for Celery monitoring
                task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": count,
                        "url": url,
                        "site_id": site_id
                    }
                )
                
                # Update progress in Redis hash
                redis_client.hset(
                    progress_key,
                    mapping={
                        "pages_found": count,
                        "current_url": url,
                        "status": "scraping",
                        "updated_at": datetime.utcnow().isoformat()
                    }
                )
                redis_client.expire(progress_key, 3600)  # Refresh TTL
            
            # Initialize scraper and search engine
            scraper = WebParser()
            search_engine = MeiliSearchEngine()
            
            # Get scraping configuration from site
            max_depth = site.config.get("max_depth", 2) if isinstance(site.config, dict) else 2
            
            # Collect pages for batch indexing
            pages_to_index = []
            
            # Scrape the site asynchronously
            async for page_data in scraper.async_scrape(
                url=site.url,
                crawl=True,
                max_depth=max_depth,
                progress_callback=progress_callback
            ):
                # Create page record in database
                page = Page(
                    site_id=site_id,
                    url=page_data.get("url", ""),
                    title=page_data.get("title", ""),
                    content=page_data.get("content", ""),
                    page_metadata=page_data.get("metadata", {})
                )
                db.add(page)
                await db.flush()  # Flush to get page.id
                
                # Prepare page for indexing
                pages_to_index.append({
                    "id": page.id,
                    "site_id": site_id,
                    "url": page.url,
                    "title": page.title,
                    "content": page.content,
                    "metadata": page.page_metadata,
                    "indexed_at": page.indexed_at.isoformat() if page.indexed_at else None
                })
                
                # Batch index every 10 pages for efficiency
                if len(pages_to_index) >= 10:
                    await search_engine.index_pages(pages_to_index)
                    pages_to_index = []
                    await db.commit()  # Commit batch to database
            
            # Index any remaining pages
            if pages_to_index:
                await search_engine.index_pages(pages_to_index)
                await db.commit()
            
            # Update site status to completed
            site.status = "completed"
            site.page_count = page_count
            site.last_scraped = datetime.utcnow()
            await db.commit()
            
            # Update final progress in Redis
            redis_client.hset(
                progress_key,
                mapping={
                    "pages_found": page_count,
                    "current_url": "",
                    "status": "completed",
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            redis_client.expire(progress_key, 3600)
            
            return {
                "site_id": site_id,
                "pages_scraped": page_count,
                "status": "completed"
            }
            
        except Exception as exc:
            # Update site status to failed
            try:
                result = await db.execute(select(Site).where(Site.id == site_id))
                site = result.scalar_one_or_none()
                if site:
                    site.status = "failed"
                    await db.commit()
                
                # Update Redis progress with failed status
                redis_client.hset(
                    progress_key,
                    mapping={
                        "pages_found": page_count,
                        "current_url": "",
                        "status": "failed",
                        "updated_at": datetime.utcnow().isoformat()
                    }
                )
                redis_client.expire(progress_key, 3600)
            except Exception:
                # Ignore errors during cleanup
                pass
            
            # Implement exponential backoff retry: 60s, 120s, 240s
            retry_count = task.request.retries
            if retry_count < 3:
                # Exponential backoff: 60s * 2^retry_count
                countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s
                raise task.retry(exc=exc, countdown=countdown)
            else:
                # Max retries exceeded
                raise MaxRetriesExceededError(
                    f"Failed to scrape site {site_id} after {retry_count} retries: {str(exc)}"
                )
