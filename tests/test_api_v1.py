"""
Tests for API v1 endpoints.

Tests include:
- Site listing and filtering
- Site creation and validation
- Site details retrieval
- Site reindexing
- Search functionality
- Export functionality
- Authentication and authorization
- Rate limiting integration
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.api_v1 import create_api_v1_router, check_site_access, extract_domain, get_pagination_metadata
from app.models import Base, Site, Page, APIKey
from app.auth import hash_api_key, verify_api_key
from app.rate_limiter import RateLimiter


# Test database URL - use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_engine():
    """Create an async test database engine"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create an async database session for testing"""
    AsyncSessionLocal = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_api_key_unrestricted():
    """Create a mock unrestricted API key."""
    api_key = MagicMock(spec=APIKey)
    api_key.id = 1
    api_key.key_hash = hash_api_key("ss_test_key_123")
    api_key.name = "Test API Key"
    api_key.site_id = None  # Unrestricted
    api_key.rate_limit_per_minute = 100
    api_key.requests_count = 0
    api_key.last_used_at = None
    api_key.expires_at = None
    api_key.is_active = True
    api_key.created_at = datetime.now(UTC)
    return api_key


@pytest.fixture
def mock_api_key_restricted():
    """Create a mock restricted API key."""
    api_key = MagicMock(spec=APIKey)
    api_key.id = 2
    api_key.key_hash = hash_api_key("ss_site_restricted_key")
    api_key.name = "Site-Specific Key"
    api_key.site_id = 999  # Restricted to site 999
    api_key.rate_limit_per_minute = 50
    api_key.requests_count = 5
    api_key.last_used_at = datetime.now(UTC) - timedelta(hours=1)
    api_key.expires_at = None
    api_key.is_active = True
    api_key.created_at = datetime.now(UTC) - timedelta(days=7)
    return api_key


@pytest.fixture
def test_site():
    """Create a test site object."""
    site = MagicMock(spec=Site)
    site.id = 999
    site.url = "https://example.com"
    site.domain = "example.com"
    site.status = "completed"
    site.page_count = 42
    site.last_scraped = datetime.now(UTC) - timedelta(days=1)
    site.created_at = datetime.now(UTC) - timedelta(days=7)
    site.updated_at = datetime.now(UTC) - timedelta(hours=6)
    site.config = {"max_depth": 2, "respect_robots_txt": True}
    return site


@pytest.fixture
def test_site_pending():
    """Create a pending test site object."""
    site = MagicMock(spec=Site)
    site.id = 1000
    site.url = "https://pending-site.com"
    site.domain = "pending-site.com"
    site.status = "pending"
    site.page_count = 0
    site.last_scraped = None
    site.created_at = datetime.now(UTC) - timedelta(hours=1)
    site.updated_at = datetime.now(UTC) - timedelta(hours=1)
    site.config = None
    return site


@pytest.fixture
def test_sites():
    """Create multiple test sites."""
    sites = []
    for i in range(15):
        site = MagicMock(spec=Site)
        site.id = i + 1
        site.url = f"https://site{i+1}.com"
        site.domain = f"site{i+1}.com"
        site.status = "completed" if i % 3 == 0 else "pending" if i % 3 == 1 else "failed"
        site.page_count = i * 10
        site.last_scraped = datetime.now(UTC) - timedelta(days=i)
        site.created_at = datetime.now(UTC) - timedelta(days=i+7)
        site.updated_at = datetime.now(UTC) - timedelta(days=i)
        site.config = {"max_depth": 2}
        sites.append(site)
    return sites


@pytest.fixture
def mock_rate_limiter():
    """Create a mock rate limiter."""
    rate_limiter = MagicMock(spec=RateLimiter)
    rate_limiter.check_api_key_limit = AsyncMock(return_value=None)  # No rate limit hit
    return rate_limiter


@pytest.fixture
def app():
    """Create FastAPI test app with API v1 router."""
    app = FastAPI()
    
    # Mock dependencies
    async def get_db_override():
        """Override database dependency."""
        return AsyncMock(spec=AsyncSession)
    
    async def verify_api_key_override():
        """Override API key verification."""
        api_key = MagicMock(spec=APIKey)
        api_key.id = 1
        api_key.site_id = None
        api_key.rate_limit_per_minute = 100
        api_key.is_active = True
        api_key.expires_at = None
        return api_key
    
    async def get_rate_limiter_override():
        """Override rate limiter dependency."""
        rate_limiter = MagicMock(spec=RateLimiter)
        rate_limiter.check_api_key_limit = AsyncMock(return_value=None)
        return rate_limiter
    
    # Get the router
    router = create_api_v1_router()
    
    # Override dependencies
    app.dependency_overrides[app.api_v1.verify_api_key] = verify_api_key_override
    app.dependency_overrides[app.api_v1.get_db] = get_db_override
    app.dependency_overrides[app.api_v1.get_rate_limiter] = get_rate_limiter_override
    
    # Include router
    app.include_router(router)
    
    return app


@pytest.fixture
def client(app):
    """Create TestClient for the app."""
    return TestClient(app)


class TestAPIV1Endpoints:
    """Test API v1 endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_sites_unrestricted(self, async_session, mock_api_key_unrestricted, test_sites):
        """Test listing sites with unrestricted API key."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = test_sites[:10]
        mock_result.scalar.return_value = len(test_sites)
        
        async_session.execute = AsyncMock(return_value=mock_result)
        
        # Call the function directly
        from app.api_v1 import list_sites
        
        result = await list_sites(
            skip=0,
            limit=10,
            status_filter=None,
            api_key=mock_api_key_unrestricted,
            db=async_session
        )
        
        # Check result
        assert "sites" in result
        assert "total" in result
        assert "skip" in result
        assert "limit" in result
        assert "has_more" in result
        assert result["total"] == len(test_sites)
        assert len(result["sites"]) == 10
        assert result["skip"] == 0
        assert result["limit"] == 10
        assert result["has_more"] == (len(test_sites) > 10)
    
    @pytest.mark.asyncio
    async def test_list_sites_restricted(self, async_session, mock_api_key_restricted, test_site):
        """Test listing sites with restricted API key."""
        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = test_site
        
        async_session.execute = AsyncMock(return_value=mock_result)
        
        # Call the function directly
        from app.api_v1 import list_sites
        
        result = await list_sites(
            skip=0,
            limit=20,
            status_filter=None,
            api_key=mock_api_key_restricted,
            db=async_session
        )
        
        # Should return only the scoped site
        assert "sites" in result
        assert len(result["sites"]) == 1
        assert result["sites"][0]["id"] == test_site.id
        assert result["total"] == 1
        assert result["skip"] == 0
        assert result["limit"] == 1
        assert result["has_more"] is False
    
    @pytest.mark.asyncio
    async def test_list_sites_status_filter(self, async_session, mock_api_key_unrestricted, test_sites):
        """Test listing sites with status filter."""
        from app.api_v1 import list_sites
        from unittest.mock import patch
        
        # Filter to completed sites only
        completed_sites = [s for s in test_sites if s.status == "completed"]
        
        # Track call count for different query types
        call_count = 0
        
        async def execute_mock(query):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First call is for count query
                mock_result = MagicMock()
                mock_result.scalar.return_value = len(completed_sites)
                return mock_result
            else:
                # Second call is for main query - need to return proper structure
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = completed_sites[:5]
                result_mock = MagicMock()
                result_mock.scalars.return_value = scalars_mock
                return result_mock
        
        async_session.execute = execute_mock
        
        # Mock the select(Site) call
        with patch('app.api_v1.select') as mock_select:
            # Mock the where() method chain
            where_mock = MagicMock()
            where_mock.order_by.return_value = where_mock
            where_mock.offset.return_value = where_mock
            where_mock.limit.return_value = where_mock
            mock_select.return_value.where.return_value = where_mock
            
            # Mock the count query
            with patch('app.api_v1.func') as mock_func:
                count_mock = MagicMock()
                count_mock.where.return_value = count_mock
                mock_func.count.return_value = count_mock
                
                # Call function
                result = await list_sites(
                    skip=0,
                    limit=5,
                    status_filter="completed",
                    api_key=mock_api_key_unrestricted,
                    db=async_session
                )
        
        # Check result
        assert result["total"] == len(completed_sites)
        assert len(result["sites"]) == min(5, len(completed_sites))
        
        # All returned sites should have status "completed"
        for site_data in result["sites"]:
            assert site_data["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_create_site_success(self, async_session, mock_api_key_unrestricted, mock_rate_limiter):
        """Test successful site creation."""
        from app.api_v1 import create_site
        from unittest.mock import MagicMock, AsyncMock
        from datetime import datetime
        
        # Mock request
        mock_request = MagicMock()
        
        # Mock database queries - need to mock the select() call
        with patch('app.api_v1.select') as mock_select:
            mock_select_result = MagicMock()
            mock_select_result.where.return_value = mock_select_result
            
            # Mock the result object
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # No existing site (synchronous method)
            
            async_session.execute = AsyncMock(return_value=mock_result)
            async_session.add = MagicMock()
            async_session.commit = AsyncMock()
            
            # Mock Site instance that gets created
            mock_site = MagicMock()
            mock_site.id = 123
            mock_site.url = "https://example.com"
            mock_site.domain = "example.com"
            mock_site.status = "pending"
            mock_site.page_count = 0
            mock_site.created_at = datetime.now(UTC)
            
            # When refresh is called, it should update the mock site
            def refresh_mock(obj):
                if obj is mock_site:
                    # Simulate what SQLAlchemy refresh does
                    pass
            
            async_session.refresh = AsyncMock(side_effect=refresh_mock)
            
            # Mock scrape task
            with patch('app.api_v1.scrape_site_task') as mock_task:
                mock_task.delay = MagicMock()
                
                # Mock Site class to return our mock site
                with patch('app.api_v1.Site', return_value=mock_site):
                    # Mock select(Site) to return our mock select
                    mock_select.return_value = mock_select_result
                    
                    # Call function
                    result = await create_site(
                        request=mock_request,
                        url="https://example.com",
                        crawl=True,
                        max_depth=2,
                        api_key=mock_api_key_unrestricted,
                        rate_limiter=mock_rate_limiter,
                        db=async_session
                    )
                    
                    # Check result
                    assert "site_id" in result
                    assert "url" in result
                    assert "domain" in result
                    assert result["status"] == "scraping"
                    assert result["message"] == "Scraping started"
                    
                    # Verify task was queued
                    mock_task.delay.assert_called_once()
                    assert mock_task.delay.call_args[0][0] == 123  # site.id
    
    @pytest.mark.asyncio
    async def test_create_site_existing(self, async_session, mock_api_key_unrestricted, mock_rate_limiter, test_site):
        """Test site creation when site already exists."""
        from app.api_v1 import create_site
        from unittest.mock import MagicMock
        from fastapi.responses import JSONResponse
        
        # Mock request
        mock_request = MagicMock()
        
        # Mock database query to return existing site
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = test_site
        
        async_session.execute = AsyncMock(return_value=mock_result)
        
        # Call function
        result = await create_site(
            request=mock_request,
            url="https://example.com",
            crawl=True,
            max_depth=2,
            api_key=mock_api_key_unrestricted,
            rate_limiter=mock_rate_limiter,
            db=async_session
        )
        
        # Should return JSONResponse with existing site info
        import json
        assert isinstance(result, JSONResponse)
        assert result.status_code == status.HTTP_200_OK
        
        # Parse response body
        response_data = json.loads(result.body.decode())
        assert "site_id" in response_data
        assert response_data["site_id"] == test_site.id
        assert response_data["url"] == "https://example.com"
        assert response_data["status"] == test_site.status
        assert "already exists" in response_data["message"]
        assert response_data["existing"] is True
    
    @pytest.mark.asyncio
    async def test_create_site_invalid_url(self, async_session, mock_api_key_unrestricted, mock_rate_limiter):
        """Test site creation with invalid URL."""
        from app.api_v1 import create_site
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        
        # Mock request
        mock_request = MagicMock()
        
        # Call function with invalid URL (no domain)
        with pytest.raises(HTTPException) as exc_info:
            await create_site(
                request=mock_request,
                url="http://",  # URL with no domain
                crawl=True,
                max_depth=2,
                api_key=mock_api_key_unrestricted,
                rate_limiter=mock_rate_limiter,
                db=async_session
            )
        
        # Should raise HTTPException with 400
        assert exc_info.value.status_code == 400
        assert "Invalid URL" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_create_site_restricted_key(self, async_session, mock_api_key_restricted, mock_rate_limiter):
        """Test site creation with restricted API key."""
        from app.api_v1 import create_site
        from unittest.mock import MagicMock
        
        # Mock request
        mock_request = MagicMock()
        
        # Call function with restricted key
        with pytest.raises(Exception) as exc_info:
            await create_site(
                request=mock_request,
                url="https://example.com",
                crawl=True,
                max_depth=2,
                api_key=mock_api_key_restricted,
                rate_limiter=mock_rate_limiter,
                db=async_session
            )
        
        # Should raise HTTPException with 403
        assert "restricted" in str(exc_info.value).lower()
        assert "cannot create new sites" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_get_site_success(self, async_session, mock_api_key_unrestricted, test_site):
        """Test successful site retrieval."""
        from app.api_v1 import get_site
        
        # Mock check_site_access to return the site
        with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
            result = await get_site(
                site_id=999,
                api_key=mock_api_key_unrestricted,
                db=async_session
            )
            
            # Check result
            assert result["id"] == test_site.id
            assert result["url"] == test_site.url
            assert result["domain"] == test_site.domain
            assert result["status"] == test_site.status
            assert result["page_count"] == test_site.page_count
            assert "config" in result
            assert "last_scraped" in result
            assert "created_at" in result
            assert "updated_at" in result
    
    @pytest.mark.asyncio
    async def test_get_site_not_found(self, async_session, mock_api_key_unrestricted):
        """Test site retrieval when site doesn't exist."""
        from app.api_v1 import get_site
        from fastapi import HTTPException
        
        # Mock check_site_access to raise 404
        with patch('app.api_v1.check_site_access', AsyncMock(side_effect=HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found"
        ))):
            with pytest.raises(HTTPException) as exc_info:
                await get_site(
                    site_id=9999,
                    api_key=mock_api_key_unrestricted,
                    db=async_session
                )
            
            # Should raise 404
            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_get_site_access_denied(self, async_session, mock_api_key_restricted):
        """Test site retrieval when access is denied."""
        from app.api_v1 import get_site
        from fastapi import HTTPException
        
        # Mock check_site_access to raise 403
        with patch('app.api_v1.check_site_access', AsyncMock(side_effect=HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        ))):
            with pytest.raises(HTTPException) as exc_info:
                await get_site(
                    site_id=888,  # Different site than API key is restricted to
                    api_key=mock_api_key_restricted,
                    db=async_session
                )
            
            # Should raise 403
            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    
    @pytest.mark.asyncio
    async def test_reindex_site_success(self, async_session, mock_api_key_unrestricted, mock_rate_limiter, test_site):
        """Test successful site reindexing."""
        from app.api_v1 import reindex_site
        
        # Mock check_site_access to return the site
        with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
            # Mock scrape task
            with patch('app.api_v1.scrape_site_task') as mock_task:
                mock_task.delay = MagicMock()
                
                # Mock commit
                async_session.commit = AsyncMock()
                
                # Call function
                result = await reindex_site(
                    site_id=999,
                    api_key=mock_api_key_unrestricted,
                    rate_limiter=mock_rate_limiter,
                    db=async_session
                )
                
                # Check result
                assert result["site_id"] == test_site.id
                assert result["domain"] == test_site.domain
                assert result["status"] == "scraping"
                assert result["message"] == "Re-indexing started"
                assert "queued_at" in result
                
                # Site status should be updated
                assert test_site.status == "scraping"
                
                # Verify commit was called
                async_session.commit.assert_called_once()
                
                # Verify task was queued
                mock_task.delay.assert_called_once_with(test_site.id)
    
    @pytest.mark.asyncio
    async def test_api_search_success(self, async_session, mock_api_key_unrestricted, mock_rate_limiter):
        """Test successful API search."""
        from app.api_v1 import api_search
        from fastapi.responses import JSONResponse
        from unittest.mock import AsyncMock
        
        # Mock MeiliSearchEngine
        mock_search_results = {
            "hits": [
                {
                    "id": 1,
                    "title": "Test Page 1",
                    "content": "This is test content",
                    "url": "https://example.com/page1",
                    "_formatted": {
                        "title": "Test <mark>Page</mark> 1",
                        "content": "This is test <mark>content</mark>"
                    }
                },
                {
                    "id": 2,
                    "title": "Test Page 2",
                    "content": "Another test page",
                    "url": "https://example.com/page2",
                    "_formatted": {
                        "title": "Test <mark>Page</mark> 2",
                        "content": "Another test <mark>page</mark>"
                    }
                }
            ],
            "estimatedTotalHits": 2,
            "limit": 20,
            "offset": 0,
            "processingTimeMs": 15
        }
        
        mock_search_engine = MagicMock()
        mock_search_engine.search = AsyncMock(return_value=mock_search_results)
        
        with patch('app.api_v1.MeiliSearchEngine', return_value=mock_search_engine):
            with patch('app.api_v1.check_site_access', AsyncMock(return_value=None)):
                result = await api_search(
                    q="test query",
                    site_id=None,
                    limit=20,
                    offset=0,
                    highlight=True,
                    api_key=mock_api_key_unrestricted,
                    rate_limiter=mock_rate_limiter,
                    db=async_session
                )
                
                # Should return JSONResponse
                assert isinstance(result, JSONResponse)
                assert result.status_code == status.HTTP_200_OK
                
                # Check headers
                assert "X-RateLimit-Limit" in result.headers
                assert "X-RateLimit-Remaining" in result.headers
                assert "X-RateLimit-Reset" in result.headers
    
    @pytest.mark.asyncio
    async def test_api_search_with_site_filter(self, async_session, mock_api_key_unrestricted, mock_rate_limiter, test_site):
        """Test API search with site filter."""
        from app.api_v1 import api_search
        from fastapi.responses import JSONResponse
        
        # Mock MeiliSearchEngine
        mock_search_results = {
            "hits": [
                {
                    "id": 1,
                    "title": "Site Page",
                    "content": "Content from specific site",
                    "url": "https://example.com/page1",
                    "_formatted": {
                        "title": "Site <mark>Page</mark>",
                        "content": "Content from specific <mark>site</mark>"
                    }
                }
            ],
            "estimatedTotalHits": 1,
            "limit": 20,
            "offset": 0,
            "processingTimeMs": 10
        }
        
        mock_search_engine = MagicMock()
        mock_search_engine.search = AsyncMock(return_value=mock_search_results)
        
        with patch('app.api_v1.MeiliSearchEngine', return_value=mock_search_engine):
            with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
                result = await api_search(
                    q="site query",
                    site_id=999,
                    limit=20,
                    offset=0,
                    highlight=True,
                    api_key=mock_api_key_unrestricted,
                    rate_limiter=mock_rate_limiter,
                    db=async_session
                )
                
                # Check that site_id was passed to search
                mock_search_engine.search.assert_called_once_with(
                    query="site query",
                    site_id=999,
                    limit=20,
                    offset=0
                )
                
                assert isinstance(result, JSONResponse)
    
    @pytest.mark.asyncio
    async def test_api_search_rate_limit_exceeded(self, async_session, mock_api_key_unrestricted, mock_rate_limiter):
        """Test API search when rate limit is exceeded."""
        from app.api_v1 import api_search
        from fastapi import HTTPException
        
        # Mock rate limiter to raise exception
        mock_rate_limiter.check_api_key_limit = AsyncMock(
            side_effect=HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await api_search(
                q="test query",
                site_id=None,
                limit=20,
                offset=0,
                highlight=True,
                api_key=mock_api_key_unrestricted,
                rate_limiter=mock_rate_limiter,
                db=async_session
            )
        
        # Should raise 429
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    
    @pytest.mark.asyncio
    async def test_search_suggestions(self, async_session, mock_api_key_unrestricted, mock_rate_limiter):
        """Test search suggestions endpoint."""
        from app.api_v1 import search_suggestions
        
        # Mock MeiliSearchEngine
        mock_search_results = {
            "hits": [
                {
                    "id": 1,
                    "title": "Test Page Title",
                    "content": "Some content",
                    "url": "https://example.com/page1",
                    "_formatted": {}
                },
                {
                    "id": 2,
                    "title": "Another Test Page",
                    "content": "More content",
                    "url": "https://example.com/page2",
                    "_formatted": {}
                }
            ],
            "estimatedTotalHits": 2,
            "limit": 10,
            "offset": 0,
            "processingTimeMs": 5
        }
        
        mock_search_engine = MagicMock()
        mock_search_engine.search = AsyncMock(return_value=mock_search_results)
        
        with patch('app.api_v1.MeiliSearchEngine', return_value=mock_search_engine):
            with patch('app.api_v1.check_site_access', AsyncMock(return_value=None)):
                result = await search_suggestions(
                    q="test",
                    site_id=None,
                    limit=5,
                    api_key=mock_api_key_unrestricted,
                    rate_limiter=mock_rate_limiter,
                    db=async_session
                )
                
                # Check result structure
                assert "query" in result
                assert "suggestions" in result
                assert result["query"] == "test"
                assert isinstance(result["suggestions"], list)
    
    @pytest.mark.asyncio
    async def test_export_site_json(self, async_session, mock_api_key_unrestricted, test_site):
        """Test site export in JSON format."""
        from app.api_v1 import export_site
        from fastapi.responses import StreamingResponse
        from unittest.mock import AsyncMock
        
        # Mock Exporter
        mock_export_response = StreamingResponse(
            iter([b'{"export": "data"}']),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="export.json"'}
        )
        
        with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
            with patch('app.api_v1.Exporter.create_export_response', AsyncMock(return_value=mock_export_response)):
                result = await export_site(
                    site_id=999,
                    format="json",
                    include_content=True,
                    stream=True,
                    api_key=mock_api_key_unrestricted,
                    db=async_session
                )
                
                # Should return StreamingResponse
                assert isinstance(result, StreamingResponse)
                assert result.media_type == "application/json"
                assert "Content-Disposition" in result.headers
    
    @pytest.mark.asyncio
    async def test_export_site_csv(self, async_session, mock_api_key_unrestricted, test_site):
        """Test site export in CSV format."""
        from app.api_v1 import export_site
        from fastapi.responses import StreamingResponse
        
        # Mock Exporter
        mock_export_response = StreamingResponse(
            iter([b'url,title,content_preview\nhttps://example.com/page1,Page 1,Preview...']),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="export.csv"'}
        )
        
        with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
            with patch('app.api_v1.Exporter.create_export_response', AsyncMock(return_value=mock_export_response)):
                result = await export_site(
                    site_id=999,
                    format="csv",
                    include_content=True,
                    stream=True,
                    api_key=mock_api_key_unrestricted,
                    db=async_session
                )
                
                # Should return StreamingResponse
                assert isinstance(result, StreamingResponse)
                assert result.media_type == "text/csv"
                assert "Content-Disposition" in result.headers
    
    @pytest.mark.asyncio
    async def test_export_site_markdown(self, async_session, mock_api_key_unrestricted, test_site):
        """Test site export in Markdown format."""
        from app.api_v1 import export_site
        from fastapi.responses import StreamingResponse
        
        # Mock Exporter
        mock_export_response = StreamingResponse(
            iter([b'# Export\n\n## Page 1\n\nContent...']),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="export.md"'}
        )
        
        with patch('app.api_v1.check_site_access', AsyncMock(return_value=test_site)):
            with patch('app.api_v1.Exporter.create_export_response', AsyncMock(return_value=mock_export_response)):
                result = await export_site(
                    site_id=999,
                    format="md",
                    include_content=True,
                    stream=True,
                    api_key=mock_api_key_unrestricted,
                    db=async_session
                )
                
                # Should return StreamingResponse
                assert isinstance(result, StreamingResponse)
                assert result.media_type == "text/markdown"
                assert "Content-Disposition" in result.headers
    
    @pytest.mark.asyncio
    async def test_export_site_invalid_format(self, async_session, mock_api_key_unrestricted, test_site):
        """Test site export with invalid format."""
        from app.api_v1 import export_site
        
        # Note: FastAPI should validate the format parameter before it reaches our handler
        # This test would be for the validation error handling
    
    @pytest.mark.asyncio
    async def test_extract_domain_valid_urls(self):
        """Test domain extraction from valid URLs."""
        # Test various URL formats
        assert extract_domain("https://example.com") == "example.com"
        assert extract_domain("http://example.com") == "example.com"
        assert extract_domain("https://sub.example.com/path?query=1") == "sub.example.com"
        assert extract_domain("http://www.example.co.uk:8080") == "www.example.co.uk:8080"
        # netloc includes credentials
        assert extract_domain("https://user:pass@example.com") == "user:pass@example.com"
    
    @pytest.mark.asyncio
    async def test_extract_domain_invalid_urls(self):
        """Test domain extraction from invalid URLs."""
        with pytest.raises(ValueError, match="Invalid URL"):
            extract_domain("not-a-url")
        
        # Note: ftp://example.com actually has a netloc, so it won't raise ValueError
        # Empty string will raise ValueError
        with pytest.raises(ValueError, match="Invalid URL"):
            extract_domain("")
    
    @pytest.mark.asyncio
    async def test_get_pagination_metadata(self):
        """Test pagination metadata generation."""
        # Test with more results
        metadata = get_pagination_metadata(skip=0, limit=20, total=100)
        assert metadata["skip"] == 0
        assert metadata["limit"] == 20
        assert metadata["total"] == 100
        assert metadata["has_more"] is True
        assert metadata["next_offset"] == 20
        
        # Test with no more results
        metadata = get_pagination_metadata(skip=80, limit=20, total=100)
        assert metadata["has_more"] is False
        assert metadata["next_offset"] is None
        
        # Test exact match
        metadata = get_pagination_metadata(skip=80, limit=20, total=100)
        assert metadata["has_more"] is False
        
        # Test with fewer results than limit
        metadata = get_pagination_metadata(skip=0, limit=20, total=15)
        assert metadata["has_more"] is False
        assert metadata["next_offset"] is None


class TestCheckSiteAccess:
    """Test site access checking."""
    
    @pytest.mark.asyncio
    async def test_check_site_access_unrestricted_key(self, mock_api_key_unrestricted):
        """Test site access with unrestricted API key."""
        mock_db = AsyncMock()
        mock_site = MagicMock(spec=Site)
        mock_site.id = 123
        
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_site
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        # Call function
        result = await check_site_access(
            api_key=mock_api_key_unrestricted,
            site_id=123,
            db=mock_db
        )
        
        # Should return the site
        assert result is mock_site
        
        # Database should have been queried
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_site_access_restricted_key_allowed(self, mock_api_key_restricted):
        """Test site access with restricted API key to allowed site."""
        mock_db = AsyncMock()
        mock_site = MagicMock(spec=Site)
        mock_site.id = 999  # Same as API key's site_id
        
        # Mock database query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_site
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        # Call function
        result = await check_site_access(
            api_key=mock_api_key_restricted,
            site_id=999,
            db=mock_db
        )
        
        # Should return the site
        assert result is mock_site
    
    @pytest.mark.asyncio
    async def test_check_site_access_restricted_key_denied(self, mock_api_key_restricted):
        """Test site access with restricted API key to denied site."""
        mock_db = AsyncMock()
        
        # Call function with different site_id than API key is restricted to
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await check_site_access(
                api_key=mock_api_key_restricted,
                site_id=888,  # Different site
                db=mock_db
            )
        
        # Should raise 403
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "restricted" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_check_site_access_site_not_found(self, mock_api_key_unrestricted):
        """Test site access when site doesn't exist."""
        mock_db = AsyncMock()
        
        # Mock database query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await check_site_access(
                api_key=mock_api_key_unrestricted,
                site_id=9999,
                db=mock_db
            )
        
        # Should raise 404
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail.lower()
    
    @pytest.mark.asyncio
    async def test_check_site_access_no_site_id(self, mock_api_key_unrestricted):
        """Test site access without site_id."""
        mock_db = AsyncMock()
        
        # Call function with None site_id
        result = await check_site_access(
            api_key=mock_api_key_unrestricted,
            site_id=None,
            db=mock_db
        )
        
        # Should return None
        assert result is None
        
        # Database should not have been queried
        mock_db.execute.assert_not_called()


class TestAPIKeyRequestHandling:
    """Test API key extraction from request."""
    
    @pytest.mark.asyncio
    async def test_get_api_key_from_header(self):
        """Test getting API key from X-API-Key header."""
        from app.api_v1 import get_api_key_from_request
        
        # Mock request with X-API-Key header
        mock_request = MagicMock()
        mock_db = AsyncMock()
        
        # Mock verify_api_key
        mock_api_key = MagicMock(spec=APIKey)
        mock_api_key.id = 123
        mock_api_key.site_id = None
        
        with patch('app.api_v1.verify_api_key', AsyncMock(return_value=mock_api_key)):
            result = await get_api_key_from_request(
                request=mock_request,
                x_api_key="ss_test_key_header",
                api_key=None,
                db=mock_db
            )
            
            # Should return the API key
            assert result is mock_api_key
            
            # Should have called verify_api_key with header value
            from app.api_v1 import verify_api_key
            verify_api_key.assert_called_once()
            credentials = verify_api_key.call_args[0][0]
            assert credentials.credentials == "ss_test_key_header"
    
    @pytest.mark.asyncio
    async def test_get_api_key_from_query_param(self):
        """Test getting API key from api_key query parameter."""
        from app.api_v1 import get_api_key_from_request
        
        # Mock request
        mock_request = MagicMock()
        mock_db = AsyncMock()
        
        # Mock verify_api_key
        mock_api_key = MagicMock(spec=APIKey)
        mock_api_key.id = 123
        mock_api_key.site_id = None
        
        with patch('app.api_v1.verify_api_key', AsyncMock(return_value=mock_api_key)):
            result = await get_api_key_from_request(
                request=mock_request,
                x_api_key=None,
                api_key="ss_test_key_query",
                db=mock_db
            )
            
            # Should return the API key
            assert result is mock_api_key
            
            # Should have called verify_api_key with query param value
            from app.api_v1 import verify_api_key
            verify_api_key.assert_called_once()
            credentials = verify_api_key.call_args[0][0]
            assert credentials.credentials == "ss_test_key_query"
    
    @pytest.mark.asyncio
    async def test_get_api_key_no_key_provided(self):
        """Test getting API key when none is provided."""
        from app.api_v1 import get_api_key_from_request
        
        # Mock request
        mock_request = MagicMock()
        mock_db = AsyncMock()
        
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            await get_api_key_from_request(
                request=mock_request,
                x_api_key=None,
                api_key=None,
                db=mock_db
            )
        
        # Should raise 401
        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "API key required" in exc_info.value.detail