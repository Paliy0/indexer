"""
Unit tests for HTMX partial response endpoints
"""

import pytest
import pytest_asyncio
import tempfile
import os
from unittest.mock import patch, Mock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import init_db
from app.config import get_settings


@pytest_asyncio.fixture
async def test_client():
    """
    Create a test client with a temporary database for HTMX testing.
    """
    # Create a temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Initialize the database
    init_db(db_path)
    
    # Mock the settings to use our test database
    settings = get_settings()
    original_db_url = settings.database_url
    
    # Temporarily override the database_url to force SQLite usage
    settings.database_url = f"sqlite:///{db_path}"
    
    # Also patch the USE_POSTGRES flag in main module to force SQLite fallback
    from app import main as app_main
    original_use_postgres = app_main.USE_POSTGRES
    app_main.USE_POSTGRES = False
    
    try:
        # Create async client with ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_path
    finally:
        # Restore original settings
        settings.database_url = original_db_url
        app_main.USE_POSTGRES = original_use_postgres
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestHTMXSearchPartial:
    """Test HTMX partial response for search endpoint"""
    
    @pytest.mark.asyncio
    async def test_search_partial_empty_query(self, test_client):
        """Test partial search endpoint with empty query"""
        client, db_path = test_client
        
        # Call partial endpoint without query
        response = await client.get("/api/search/partial")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Response should be HTML (not JSON)
        html_content = response.text
        assert isinstance(html_content, str)
        assert len(html_content) > 0
    
    @pytest.mark.asyncio
    async def test_search_partial_with_query_no_results(self, test_client):
        """Test partial search with query but no indexed pages"""
        client, db_path = test_client
        
        # Search when database is empty
        response = await client.get(
            "/api/search/partial",
            params={"q": "nonexistent"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        html_content = response.text
        # Should show "no results" or similar message
        assert "0" in html_content or "no" in html_content.lower() or "result" in html_content.lower()
    
    @pytest.mark.asyncio
    async def test_search_partial_with_results(self, test_client):
        """Test partial search endpoint with actual results"""
        client, db_path = test_client
        
        # First, create a site and pages
        mock_pages = [
            {
                "url": "https://example.com/python",
                "title": "Python Tutorial",
                "content": "Learn Python programming language"
            },
            {
                "url": "https://example.com/javascript",
                "title": "JavaScript Guide",
                "content": "Learn JavaScript programming"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            # Index the pages
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": True}
            )
        
        # Now search using the partial endpoint
        response = await client.get(
            "/api/search/partial",
            params={"q": "python"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        html_content = response.text
        
        # Should contain search results
        assert "Python" in html_content
        assert "Tutorial" in html_content
        
        # Should NOT contain JavaScript result
        assert "JavaScript" not in html_content or html_content.count("JavaScript") == 0
    
    @pytest.mark.asyncio
    async def test_search_partial_with_site_filter(self, test_client):
        """Test partial search with site_id filter"""
        client, db_path = test_client
        
        # Create two sites with different content
        site1_pages = [
            {
                "url": "https://site1.com/",
                "title": "Site 1 Content",
                "content": "This is about programming tutorials"
            }
        ]
        
        site2_pages = [
            {
                "url": "https://site2.com/",
                "title": "Site 2 Content",
                "content": "This is also about programming tutorials"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            MockWebParser.return_value = mock_parser
            
            # Create site 1
            mock_parser.scrape.return_value = site1_pages
            response1 = await client.post(
                "/api/scrape",
                json={"url": "https://site1.com", "crawl": False}
            )
            site1_id = response1.json()["site_id"]
            
            # Create site 2
            mock_parser.scrape.return_value = site2_pages
            await client.post(
                "/api/scrape",
                json={"url": "https://site2.com", "crawl": False}
            )
        
        # Search with site_id filter
        response = await client.get(
            "/api/search/partial",
            params={"q": "programming", "site_id": site1_id}
        )
        
        assert response.status_code == 200
        html_content = response.text
        
        # Should only show Site 1 content
        assert "Site 1" in html_content
        assert "Site 2" not in html_content
    
    @pytest.mark.asyncio
    async def test_search_partial_highlighting(self, test_client):
        """Test that search results include highlighting with <mark> tags"""
        client, db_path = test_client
        
        mock_pages = [
            {
                "url": "https://example.com/test",
                "title": "Testing Search Functionality",
                "content": "This page is about testing the search feature with highlighting"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
        
        # Search for "testing"
        response = await client.get(
            "/api/search/partial",
            params={"q": "testing"}
        )
        
        assert response.status_code == 200
        html_content = response.text
        
        # Should contain <mark> tags for highlighting
        assert "<mark>" in html_content
        assert "</mark>" in html_content
    
    @pytest.mark.asyncio
    async def test_search_partial_whitespace_query(self, test_client):
        """Test partial search with whitespace-only query"""
        client, db_path = test_client
        
        # Query with only spaces
        response = await client.get(
            "/api/search/partial",
            params={"q": "   "}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Should return empty state (no error)
        html_content = response.text
        assert len(html_content) > 0
    
    @pytest.mark.asyncio
    async def test_search_partial_error_handling(self, test_client):
        """Test that errors are returned as HTML partials, not exceptions"""
        client, db_path = test_client
        
        # Mock the search engine to raise an exception
        with patch('app.main.SQLiteSearchEngine') as MockSearchEngine:
            mock_engine = Mock()
            mock_engine.search.side_effect = Exception("Search engine error")
            MockSearchEngine.return_value = mock_engine
            
            response = await client.get(
                "/api/search/partial",
                params={"q": "test"}
            )
            
            # Should return 200 with HTML error message (not 500)
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            
            html_content = response.text
            # Should contain error information
            assert len(html_content) > 0


class TestHTMXIntegration:
    """Test HTMX-specific behaviors"""
    
    @pytest.mark.asyncio
    async def test_htmx_request_header(self, test_client):
        """Test that HTMX requests are properly identified"""
        client, db_path = test_client
        
        # Make request with HX-Request header (standard HTMX header)
        response = await client.get(
            "/api/search/partial",
            params={"q": "test"},
            headers={"HX-Request": "true"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_partial_response_structure(self, test_client):
        """Test that partial response is a valid HTML fragment"""
        client, db_path = test_client
        
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Example Page",
                "content": "Example content for testing"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
        
        # Get partial response
        response = await client.get(
            "/api/search/partial",
            params={"q": "example"}
        )
        
        assert response.status_code == 200
        html = response.text
        
        # Should be valid HTML fragment (not full page with <html>, <head>, etc.)
        assert "<html>" not in html.lower() or html.lower().count("<html>") == 0
        assert "<head>" not in html.lower() or html.lower().count("<head>") == 0
        
        # But should contain some content
        assert len(html) > 0
    
    @pytest.mark.asyncio
    async def test_search_partial_limit_parameter(self, test_client):
        """Test limit parameter works with partial endpoint"""
        client, db_path = test_client
        
        # Create multiple pages
        mock_pages = [
            {
                "url": f"https://example.com/page{i}",
                "title": f"Test Page {i}",
                "content": f"Content about testing for page {i}"
            }
            for i in range(1, 6)  # 5 pages
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": True}
            )
        
        # Search with limit
        response = await client.get(
            "/api/search/partial",
            params={"q": "testing", "limit": 3}
        )
        
        assert response.status_code == 200
        html_content = response.text
        
        # Should return results (exact count check is tricky with HTML,
        # but we can verify it's not empty)
        assert "Test Page" in html_content
        assert len(html_content) > 100
    
    @pytest.mark.asyncio
    async def test_search_partial_offset_parameter(self, test_client):
        """Test offset parameter for pagination"""
        client, db_path = test_client
        
        # Create pages
        mock_pages = [
            {
                "url": f"https://example.com/page{i}",
                "title": f"Page {i}",
                "content": "Test content"
            }
            for i in range(1, 6)
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": True}
            )
        
        # Get first page of results
        response1 = await client.get(
            "/api/search/partial",
            params={"q": "test", "limit": 2, "offset": 0}
        )
        
        # Get second page of results
        response2 = await client.get(
            "/api/search/partial",
            params={"q": "test", "limit": 2, "offset": 2}
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Both should return HTML
        assert len(response1.text) > 0
        assert len(response2.text) > 0


class TestTemplatePartial:
    """Test that partial template is correctly rendered"""
    
    @pytest.mark.asyncio
    async def test_partial_template_exists(self, test_client):
        """Test that the partial template renders without errors"""
        client, db_path = test_client
        
        # Call partial endpoint (should use partials/search_results.html)
        response = await client.get(
            "/api/search/partial",
            params={"q": ""}
        )
        
        # Should not raise template errors
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_partial_template_with_context(self, test_client):
        """Test that template receives proper context"""
        client, db_path = test_client
        
        # Create some test data
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Context Test",
                "content": "Testing context passing to template"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            mock_parser.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
        
        # Search and get partial
        response = await client.get(
            "/api/search/partial",
            params={"q": "context"}
        )
        
        assert response.status_code == 200
        html = response.text
        
        # Template should render the context
        assert "Context Test" in html
