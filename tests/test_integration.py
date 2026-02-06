"""
Integration tests for end-to-end flow
Tests: submit URL -> scrape -> store in DB -> search -> verify results
"""

import pytest
import pytest_asyncio
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, Mock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import init_db, get_db_connection
from app.config import get_settings


@pytest_asyncio.fixture
async def test_client():
    """
    Create a test client with a temporary database.
    Each test gets a fresh database.
    """
    # Create a temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Initialize the database
    init_db(db_path)
    
    # Mock the settings to use our test database
    # We need to patch the settings object that main.py uses
    settings = get_settings()
    original_db_url = settings.database_url
    
    # Temporarily override the database_url
    settings.database_url = f"sqlite:///{db_path}"
    
    try:
        # Create async client with ASGITransport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_path
    finally:
        # Restore original settings
        settings.database_url = original_db_url
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestEndToEndFlow:
    """Test complete end-to-end workflow"""
    
    @pytest.mark.asyncio
    async def test_scrape_and_search_flow(self, test_client):
        """
        Test the complete flow:
        1. Submit URL via POST /api/scrape
        2. Pages are scraped and stored in DB
        3. Search for content via GET /api/search
        4. Verify search results contain scraped content
        """
        client, db_path = test_client
        
        # Mock the WebParser to avoid actual web requests
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Example Domain",
                "content": "This domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission."
            },
            {
                "url": "https://example.com/about",
                "title": "About Example",
                "content": "Example.com is a special domain reserved for use in documentation and testing. Learn more about reserved domains."
            },
            {
                "url": "https://example.com/contact",
                "title": "Contact Us",
                "content": "Get in touch with the Example team. Send us an email or visit our office."
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            # Setup mock
            mock_parser_instance = Mock()
            mock_parser_instance.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser_instance
            
            # Step 1: Submit URL for scraping
            scrape_response = await client.post(
                "/api/scrape",
                json={
                    "url": "https://example.com",
                    "crawl": True,
                    "max_depth": 2
                }
            )
            
            # Verify scrape response
            assert scrape_response.status_code == 202
            scrape_data = scrape_response.json()
            assert "site_id" in scrape_data
            assert scrape_data["status"] == "completed"
            assert scrape_data["message"] == "Successfully scraped 3 pages"
            
            site_id = scrape_data["site_id"]
        
        # Step 2: Verify pages are in database
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM pages WHERE site_id = ?", (site_id,))
        page_count = cursor.fetchone()['count']
        assert page_count == 3
        
        # Verify site status is completed
        cursor.execute("SELECT status, page_count FROM sites WHERE id = ?", (site_id,))
        site = cursor.fetchone()
        assert site['status'] == "completed"
        assert site['page_count'] == 3
        conn.close()
        
        # Step 3: Search for content
        search_response = await client.get(
            "/api/search",
            params={"q": "documentation", "limit": 10}
        )
        
        # Verify search response
        assert search_response.status_code == 200
        search_data = search_response.json()
        assert search_data["query"] == "documentation"
        assert search_data["total_results"] > 0
        
        # Verify search results contain expected content
        results = search_data["results"]
        assert len(results) > 0
        
        # Should find the "About" page which mentions "documentation"
        titles = [r["title"] for r in results]
        assert "About Example" in titles
        
        # Verify snippet contains highlighted search term
        about_result = [r for r in results if r["title"] == "About Example"][0]
        assert "<mark>" in about_result["snippet"]
        assert "</mark>" in about_result["snippet"]
    
    @pytest.mark.asyncio
    async def test_scrape_single_page(self, test_client):
        """Test scraping a single page without crawling"""
        client, db_path = test_client
        
        mock_page = {
            "url": "https://test.com/single",
            "title": "Single Page Test",
            "content": "This is a single page with unique content about Python programming."
        }
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser_instance = Mock()
            mock_parser_instance.scrape.return_value = [mock_page]
            MockWebParser.return_value = mock_parser_instance
            
            # Scrape without crawling
            scrape_response = await client.post(
                "/api/scrape",
                json={
                    "url": "https://test.com/single",
                    "crawl": False,
                    "max_depth": 1
                }
            )
            
            assert scrape_response.status_code == 202
            scrape_data = scrape_response.json()
            assert scrape_data["status"] == "completed"
            
            site_id = scrape_data["site_id"]
        
        # Verify only one page was stored
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM pages WHERE site_id = ?", (site_id,))
        assert cursor.fetchone()['count'] == 1
        conn.close()
        
        # Search for unique content
        search_response = await client.get(
            "/api/search",
            params={"q": "Python programming"}
        )
        
        assert search_response.status_code == 200
        search_data = search_response.json()
        assert search_data["total_results"] == 1
        assert search_data["results"][0]["title"] == "Single Page Test"
    
    @pytest.mark.asyncio
    async def test_search_by_site_id(self, test_client):
        """Test searching with site_id filter"""
        client, db_path = test_client
        
        # Create two different sites with different content
        site1_pages = [
            {
                "url": "https://site1.com/",
                "title": "Site 1 Home",
                "content": "Welcome to site one. We offer Python tutorials."
            }
        ]
        
        site2_pages = [
            {
                "url": "https://site2.com/",
                "title": "Site 2 Home",
                "content": "Welcome to site two. We offer JavaScript tutorials."
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            MockWebParser.return_value = mock_parser
            
            # Scrape site 1
            mock_parser.scrape.return_value = site1_pages
            response1 = await client.post(
                "/api/scrape",
                json={"url": "https://site1.com", "crawl": False}
            )
            site1_id = response1.json()["site_id"]
            
            # Scrape site 2
            mock_parser.scrape.return_value = site2_pages
            response2 = await client.post(
                "/api/scrape",
                json={"url": "https://site2.com", "crawl": False}
            )
            site2_id = response2.json()["site_id"]
        
        # Search all sites for "tutorials"
        search_all = await client.get("/api/search", params={"q": "tutorials"})
        assert search_all.status_code == 200
        all_results = search_all.json()["results"]
        assert len(all_results) == 2
        
        # Search only site 1
        search_site1 = await client.get(
            "/api/search",
            params={"q": "tutorials", "site_id": site1_id}
        )
        assert search_site1.status_code == 200
        site1_results = search_site1.json()["results"]
        assert len(site1_results) == 1
        assert site1_results[0]["title"] == "Site 1 Home"
        assert "Python" in site1_results[0]["snippet"]
        
        # Search only site 2
        search_site2 = await client.get(
            "/api/search",
            params={"q": "tutorials", "site_id": site2_id}
        )
        assert search_site2.status_code == 200
        site2_results = search_site2.json()["results"]
        assert len(site2_results) == 1
        assert site2_results[0]["title"] == "Site 2 Home"
        assert "JavaScript" in site2_results[0]["snippet"]
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, test_client):
        """Test search with no matching results"""
        client, db_path = test_client
        
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Example Page",
                "content": "Some content about web development."
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser_instance = Mock()
            mock_parser_instance.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser_instance
            
            await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
        
        # Search for term that doesn't exist
        search_response = await client.get(
            "/api/search",
            params={"q": "nonexistent_term_xyz"}
        )
        
        assert search_response.status_code == 200
        search_data = search_response.json()
        assert search_data["total_results"] == 0
        assert search_data["results"] == []
    
    @pytest.mark.asyncio
    async def test_get_site_details(self, test_client):
        """Test retrieving site details after scraping"""
        client, db_path = test_client
        
        mock_pages = [
            {
                "url": "https://testsite.com/",
                "title": "Test Site",
                "content": "Test content"
            },
            {
                "url": "https://testsite.com/page2",
                "title": "Page 2",
                "content": "More content"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser_instance = Mock()
            mock_parser_instance.scrape.return_value = mock_pages
            MockWebParser.return_value = mock_parser_instance
            
            scrape_response = await client.post(
                "/api/scrape",
                json={"url": "https://testsite.com", "crawl": True}
            )
            site_id = scrape_response.json()["site_id"]
        
        # Get site details
        site_response = await client.get(f"/api/sites/{site_id}")
        
        assert site_response.status_code == 200
        site_data = site_response.json()
        assert site_data["id"] == site_id
        assert site_data["domain"] == "testsite.com"
        assert site_data["status"] == "completed"
        assert site_data["page_count"] == 2
        # URL might have trailing slash added
        assert site_data["url"].startswith("https://testsite.com")
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_site(self, test_client):
        """Test retrieving non-existent site returns 404"""
        client, db_path = test_client
        
        response = await client.get("/api/sites/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_scrape_duplicate_site(self, test_client):
        """Test scraping same site twice updates existing site"""
        client, db_path = test_client
        
        mock_pages_v1 = [
            {
                "url": "https://example.com/",
                "title": "Version 1",
                "content": "Original content"
            }
        ]
        
        mock_pages_v2 = [
            {
                "url": "https://example.com/",
                "title": "Version 2",
                "content": "Updated content"
            },
            {
                "url": "https://example.com/new",
                "title": "New Page",
                "content": "New content"
            }
        ]
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            MockWebParser.return_value = mock_parser
            
            # First scrape
            mock_parser.scrape.return_value = mock_pages_v1
            response1 = await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
            site_id_1 = response1.json()["site_id"]
            
            # Second scrape of same domain
            mock_parser.scrape.return_value = mock_pages_v2
            response2 = await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": True}
            )
            site_id_2 = response2.json()["site_id"]
        
        # Should reuse the same site ID
        assert site_id_1 == site_id_2
        
        # Check total pages in database
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM pages WHERE site_id = ?", (site_id_1,))
        # Should have 1 + 2 = 3 pages total (not replacing, just adding)
        page_count = cursor.fetchone()['count']
        assert page_count == 3
        conn.close()
    
    @pytest.mark.asyncio
    async def test_scrape_failure_updates_status(self, test_client):
        """Test that scraping failure updates site status to 'failed'"""
        client, db_path = test_client
        
        with patch('app.main.WebParser') as MockWebParser:
            mock_parser = Mock()
            MockWebParser.return_value = mock_parser
            
            # Make scraper raise an exception
            from app.scraper import ScrapingError
            mock_parser.scrape.side_effect = ScrapingError("Network error")
            
            response = await client.post(
                "/api/scrape",
                json={"url": "https://example.com", "crawl": False}
            )
            
            # Should return 500 error
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()
        
        # Verify site status is 'failed'
        conn = get_db_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM sites WHERE domain = ?", ("example.com",))
        site = cursor.fetchone()
        assert site is not None
        assert site['status'] == "failed"
        conn.close()
    
    @pytest.mark.asyncio
    async def test_system_status_endpoint(self, test_client):
        """Test system status endpoint"""
        client, db_path = test_client
        
        # Add some data first
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Test",
                "content": "Content"
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
        
        # Get system status
        response = await client.get("/api/status")
        
        assert response.status_code == 200
        status_data = response.json()
        assert status_data["status"] == "ok"
        assert status_data["database"] == "ok"
        assert status_data["total_sites"] == 1
        assert status_data["total_pages"] == 1
    
    @pytest.mark.asyncio
    async def test_search_validation(self, test_client):
        """Test search endpoint validation"""
        client, db_path = test_client
        
        # Missing query parameter
        response = await client.get("/api/search")
        assert response.status_code == 422  # Validation error
        
        # Empty query
        response = await client.get("/api/search", params={"q": ""})
        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()
        
        # Whitespace only query
        response = await client.get("/api/search", params={"q": "   "})
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_search_limit_parameter(self, test_client):
        """Test search limit parameter"""
        client, db_path = test_client
        
        # Create site with multiple pages
        mock_pages = [
            {
                "url": f"https://example.com/page{i}",
                "title": f"Page {i}",
                "content": f"This is page {i} about testing search functionality"
            }
            for i in range(1, 11)  # 10 pages
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
            "/api/search",
            params={"q": "testing", "limit": 5}
        )
        
        assert response.status_code == 200
        search_data = response.json()
        assert len(search_data["results"]) <= 5
        
        # Search with high limit (should cap at 100)
        response = await client.get(
            "/api/search",
            params={"q": "testing", "limit": 200}
        )
        
        assert response.status_code == 200
        search_data = response.json()
        # Should return all 10 results since we have less than 100
        assert len(search_data["results"]) == 10


class TestTemplateRoutes:
    """Test HTML template routes"""
    
    @pytest.mark.asyncio
    async def test_index_page(self, test_client):
        """Test index page loads"""
        client, db_path = test_client
        
        response = await client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_site_search_page(self, test_client):
        """Test site search page"""
        client, db_path = test_client
        
        # Create a site first
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Example",
                "content": "Test content for searching"
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
        
        # Access search page
        response = await client.get("/site/example.com/search")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Access with query
        response = await client.get("/site/example.com/search?q=test")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_site_status_page(self, test_client):
        """Test site status page"""
        client, db_path = test_client
        
        # Create a site
        mock_pages = [
            {
                "url": "https://example.com/",
                "title": "Example",
                "content": "Content"
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
        
        # Access status page
        response = await client.get("/site/example.com/status")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_site_status_page_nonexistent(self, test_client):
        """Test status page for non-existent site"""
        client, db_path = test_client
        
        # Should show setup form for non-existent site
        response = await client.get("/site/nonexistent.com/status")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
