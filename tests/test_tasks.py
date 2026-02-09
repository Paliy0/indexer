"""
Tests for Celery background tasks.

Tests the scrape_site_task with mocked dependencies:
- Mocked scraper (WebParser)
- Mocked database (async SQLAlchemy)
- Mocked Meilisearch engine
- Redis progress tracking
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timedelta
from celery.exceptions import MaxRetriesExceededError

from app.tasks import scrape_site_task, _scrape_site_async
from app.models import Site, Page


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = MagicMock()
    redis_mock.hset = MagicMock()
    redis_mock.expire = MagicMock()
    return redis_mock


@pytest.fixture
def mock_site():
    """Mock Site model instance."""
    site = MagicMock(spec=Site)
    site.id = 1
    site.url = "https://example.com"
    site.status = "pending"
    site.config = {"max_depth": 2}
    site.page_count = 0
    site.last_scraped = None
    return site


@pytest.fixture
def mock_db_session(mock_site):
    """Mock async database session as an async context manager."""
    session = AsyncMock()
    
    # Mock execute result
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=mock_site)
    
    session.execute = AsyncMock(return_value=result_mock)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    
    # Make it work as an async context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    
    return session


@pytest.fixture
def mock_scraper():
    """Mock WebParser instance."""
    scraper = MagicMock()
    
    # Mock async_scrape to yield sample pages
    async def async_scrape_gen(*args, **kwargs):
        # Call progress callback if provided
        progress_callback = kwargs.get('progress_callback')
        
        pages = [
            {"url": "https://example.com/page1", "title": "Page 1", "content": "Content 1", "metadata": {}},
            {"url": "https://example.com/page2", "title": "Page 2", "content": "Content 2", "metadata": {}},
            {"url": "https://example.com/page3", "title": "Page 3", "content": "Content 3", "metadata": {}},
        ]
        
        for idx, page in enumerate(pages, 1):
            if progress_callback:
                progress_callback(idx, page["url"])
            yield page
    
    scraper.async_scrape = async_scrape_gen
    return scraper


@pytest.fixture
def mock_search_engine():
    """Mock MeiliSearchEngine instance."""
    engine = MagicMock()
    engine.index_pages = AsyncMock()
    return engine


@pytest.mark.asyncio
async def test_scrape_site_async_success(
    mock_db_session, mock_redis, mock_site, mock_scraper, mock_search_engine
):
    """Test successful site scraping with all components mocked."""
    
    # Create mock task for Celery
    mock_task = MagicMock()
    mock_task.update_state = MagicMock()
    mock_task.request.retries = 0
    
    # Mock AsyncSessionLocal to return the session
    mock_session_factory = MagicMock(return_value=mock_db_session)
    
    with patch("app.tasks.redis.from_url", return_value=mock_redis):
        with patch("app.tasks.AsyncSessionLocal", mock_session_factory):
            with patch("app.tasks.WebParser", return_value=mock_scraper):
                with patch("app.tasks.MeiliSearchEngine", return_value=mock_search_engine):
                    # Run the async scrape function
                    result = await _scrape_site_async(mock_task, site_id=1)
    
    # Verify result
    assert result["site_id"] == 1
    assert result["pages_scraped"] == 3
    assert result["status"] == "completed"
    
    # Verify site status was updated
    assert mock_site.status == "completed"
    assert mock_site.page_count == 3
    assert mock_site.last_scraped is not None
    
    # Verify Redis was updated with progress
    assert mock_redis.hset.called
    assert mock_redis.expire.called
    
    # Verify pages were indexed in Meilisearch
    assert mock_search_engine.index_pages.called
    
    # Verify database operations
    assert mock_db_session.add.called
    assert mock_db_session.flush.called
    assert mock_db_session.commit.called


@pytest.mark.asyncio
async def test_scrape_site_async_site_not_found(mock_db_session, mock_redis):
    """Test scraping fails gracefully when site not found."""
    
    # Mock site not found
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=result_mock)
    
    mock_task = MagicMock()
    mock_task.update_state = MagicMock()
    mock_task.request.retries = 0
    mock_task.retry = MagicMock(side_effect=Exception("Retry called"))
    
    # Mock AsyncSessionLocal to return the session
    mock_session_factory = MagicMock(return_value=mock_db_session)
    
    with patch("app.tasks.redis.from_url", return_value=mock_redis):
        with patch("app.tasks.AsyncSessionLocal", mock_session_factory):
            # Should raise ValueError for site not found
            with pytest.raises(Exception):  # Will trigger retry mechanism
                await _scrape_site_async(mock_task, site_id=999)


@pytest.mark.asyncio
async def test_scrape_site_async_error_handling(
    mock_db_session, mock_redis, mock_site, mock_scraper, mock_search_engine
):
    """Test error handling and retry logic."""
    
    # Mock scraper to raise an error
    async def failing_scrape(*args, **kwargs):
        raise Exception("Scraping failed")
        yield  # Make it a generator
    
    mock_scraper.async_scrape = failing_scrape
    
    mock_task = MagicMock()
    mock_task.update_state = MagicMock()
    mock_task.request.retries = 0
    mock_task.retry = MagicMock(side_effect=Exception("Retry triggered"))
    
    # Mock AsyncSessionLocal to return the session
    mock_session_factory = MagicMock(return_value=mock_db_session)
    
    with patch("app.tasks.redis.from_url", return_value=mock_redis):
        with patch("app.tasks.AsyncSessionLocal", mock_session_factory):
            with patch("app.tasks.WebParser", return_value=mock_scraper):
                with patch("app.tasks.MeiliSearchEngine", return_value=mock_search_engine):
                    # Should trigger retry
                    with pytest.raises(Exception):
                        await _scrape_site_async(mock_task, site_id=1)
    
    # Verify site status was updated to failed
    assert mock_site.status == "failed"
    
    # Verify Redis was updated with failed status
    hset_calls = mock_redis.hset.call_args_list
    # Check if any call contains "failed" status
    failed_status_set = any(
        "status" in str(call) and "failed" in str(call)
        for call in hset_calls
    )
    assert failed_status_set


@pytest.mark.asyncio
async def test_scrape_site_async_progress_tracking(
    mock_db_session, mock_redis, mock_site, mock_scraper, mock_search_engine
):
    """Test that progress is tracked in Redis during scraping."""
    
    mock_task = MagicMock()
    mock_task.update_state = MagicMock()
    mock_task.request.retries = 0
    
    # Mock AsyncSessionLocal to return the session
    mock_session_factory = MagicMock(return_value=mock_db_session)
    
    with patch("app.tasks.redis.from_url", return_value=mock_redis):
        with patch("app.tasks.AsyncSessionLocal", mock_session_factory):
            with patch("app.tasks.WebParser", return_value=mock_scraper):
                with patch("app.tasks.MeiliSearchEngine", return_value=mock_search_engine):
                    result = await _scrape_site_async(mock_task, site_id=1)
    
    # Verify Redis hset was called multiple times (initial, updates, final)
    assert mock_redis.hset.call_count >= 3
    
    # Verify Celery task state was updated
    assert mock_task.update_state.call_count == 3  # Once per page
    
    # Check that task state updates included progress info
    for call_args in mock_task.update_state.call_args_list:
        assert call_args[1]["state"] == "PROGRESS"
        assert "current" in call_args[1]["meta"]
        assert "url" in call_args[1]["meta"]


@pytest.mark.asyncio
async def test_scrape_site_async_batch_indexing(
    mock_db_session, mock_redis, mock_site, mock_search_engine
):
    """Test that pages are indexed in batches for efficiency."""
    
    # Create scraper that yields 15 pages (should trigger 2 batches: 10 + 5)
    scraper = MagicMock()
    
    async def many_pages_gen(*args, **kwargs):
        # Call progress callback if provided
        progress_callback = kwargs.get('progress_callback')
        
        for i in range(15):
            if progress_callback:
                progress_callback(i + 1, f"https://example.com/page{i}")
            
            yield {
                "url": f"https://example.com/page{i}",
                "title": f"Page {i}",
                "content": f"Content {i}",
                "metadata": {}
            }
    
    scraper.async_scrape = many_pages_gen
    
    mock_task = MagicMock()
    mock_task.update_state = MagicMock()
    mock_task.request.retries = 0
    
    # Mock AsyncSessionLocal to return the session
    mock_session_factory = MagicMock(return_value=mock_db_session)
    
    with patch("app.tasks.redis.from_url", return_value=mock_redis):
        with patch("app.tasks.AsyncSessionLocal", mock_session_factory):
            with patch("app.tasks.WebParser", return_value=scraper):
                with patch("app.tasks.MeiliSearchEngine", return_value=mock_search_engine):
                    result = await _scrape_site_async(mock_task, site_id=1)
    
    # Verify pages were indexed (batch at 10, then final 5)
    assert mock_search_engine.index_pages.call_count == 2
    
    # Verify final count
    assert result["pages_scraped"] == 15
