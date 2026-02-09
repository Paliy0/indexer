"""
Tests for app/export.py Exporter class.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.export import Exporter
from app.models import Site, Page


@pytest.fixture
def mock_site():
    """Create a mock site for testing."""
    site = MagicMock(spec=Site)
    site.id = 1
    site.url = "https://example.com"
    site.domain = "example.com"
    site.status = "completed"
    site.page_count = 5
    site.last_scraped = datetime(2024, 1, 1, 12, 0, 0)
    site.created_at = datetime(2024, 1, 1, 11, 0, 0)
    return site


@pytest.fixture
def mock_pages():
    """Create mock pages for testing."""
    pages = []
    for i in range(3):
        page = MagicMock(spec=Page)
        page.id = i + 1
        page.url = f"https://example.com/page{i+1}"
        page.title = f"Page {i+1}"
        page.content = f"This is the content of page {i+1}. " * 10
        page.page_metadata = {"word_count": 100, "links": 5}
        page.indexed_at = datetime(2024, 1, 1, 12, i, 0)
        page.created_at = datetime(2024, 1, 1, 12, i, 0)
        pages.append(page)
    return pages


@pytest.fixture
def mock_db_session(mock_pages):
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    
    # Create a mock result object with proper awaitable structure
    def create_mock_result(for_count=False):
        result_mock = AsyncMock()
        
        if for_count:
            # For count query - scalar() returns a coroutine
            scalar_mock = AsyncMock(return_value=len(mock_pages))
            result_mock.scalar = scalar_mock
        else:
            # For page query - scalars() returns an object with all() method
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=mock_pages)
            result_mock.scalars = MagicMock(return_value=scalars_mock)
        
        return result_mock
    
    # Mock execute method
    async def execute_mock(query):
        # Check if this is a count query
        for_count = "count" in str(query).lower()
        return create_mock_result(for_count=for_count)
    
    session.execute = execute_mock
    return session


class TestExporter:
    """Test the Exporter class."""
    
    def test_truncate_content(self):
        """Test content truncation."""
        # Short content
        assert Exporter._truncate_content("Short", 200) == "Short"
        
        # Long content - exact truncation
        long_content = "This is a long content that needs to be truncated. " * 10
        truncated = Exporter._truncate_content(long_content, 100)
        assert len(truncated) <= 103  # Allow for ellipsis
        assert truncated.endswith("...")
        
        # Long content with spaces
        spaced_content = "Word1 word2 word3 " * 20
        truncated = Exporter._truncate_content(spaced_content, 50)
        # Should truncate at word boundary
        assert " " in truncated[:-3]  # Should have space before ellipsis
    
    @pytest.mark.asyncio
    async def test_get_pages_for_site(self, mock_db_session, mock_pages):
        """Test getting pages for a site."""
        pages = await Exporter.get_pages_for_site(mock_db_session, site_id=1, limit=10000)
        assert len(pages) == len(mock_pages)
    
    def test_export_json(self, mock_site, mock_pages):
        """Test JSON export."""
        result = Exporter.export_json(mock_pages, mock_site)
        
        # Check structure
        assert "exported_at" in result
        assert "site" in result
        assert "total_pages" in result
        assert "pages" in result
        
        # Check site data
        assert result["site"]["id"] == mock_site.id
        assert result["site"]["domain"] == mock_site.domain
        
        # Check page data
        assert len(result["pages"]) == len(mock_pages)
        for page_data in result["pages"]:
            assert "url" in page_data
            assert "title" in page_data
            assert "content" in page_data
            assert "content_preview" in page_data
            assert "metadata" in page_data
            assert "indexed_at" in page_data
            assert "created_at" in page_data
    
    def test_export_csv(self, mock_pages):
        """Test CSV export."""
        result = Exporter.export_csv(mock_pages)
        
        # Check CSV format
        lines = result.strip().split('\n')
        assert len(lines) == len(mock_pages) + 1  # Header + data rows
        
        # Check header
        assert "url,title,content_preview,indexed_at" in lines[0]
        
        # Check data rows
        for i, line in enumerate(lines[1:], 1):
            assert mock_pages[i-1].url in line
            assert mock_pages[i-1].title in line
    
    def test_export_markdown(self, mock_site, mock_pages):
        """Test Markdown export."""
        # Test with full content
        result_full = Exporter.export_markdown(mock_pages, mock_site, include_content=True)
        assert "# Export:" in result_full
        assert "Total pages:" in result_full
        assert "---" in result_full
        
        # Test with preview only
        result_preview = Exporter.export_markdown(mock_pages, mock_site, include_content=False)
        assert "# Export:" in result_preview
        
        # Check that each page has a section
        for page in mock_pages:
            assert f"## " in result_full
            assert page.url in result_full
    
    @pytest.mark.asyncio
    async def test_stream_json(self, mock_db_session, mock_site):
        """Test streaming JSON export."""
        # Mock the stream_json method to test its structure
        chunks = []
        async for chunk in Exporter.stream_json(mock_db_session, site_id=1, site=mock_site, batch_size=1000):
            chunks.append(chunk)
        
        # Combine chunks and parse as JSON
        json_str = ''.join(chunks)
        assert json_str.startswith('{"exported_at":')
        assert '"site":' in json_str
        assert '"pages":' in json_str
    
    @pytest.mark.asyncio
    async def test_create_export_response_json(self, mock_db_session, mock_site):
        """Test creating JSON export response."""
        response = await Exporter.create_export_response(
            db=mock_db_session,
            site_id=1,
            site=mock_site,
            format="json",
            include_content=True,
            stream_large=False
        )
        
        assert response.media_type == "application/json"
        assert "Content-Disposition" in response.headers
    
    @pytest.mark.asyncio
    async def test_create_export_response_csv(self, mock_db_session, mock_site):
        """Test creating CSV export response."""
        response = await Exporter.create_export_response(
            db=mock_db_session,
            site_id=1,
            site=mock_site,
            format="csv",
            include_content=True,
            stream_large=False
        )
        
        assert response.media_type == "text/csv"
        assert "Content-Disposition" in response.headers
    
    @pytest.mark.asyncio
    async def test_create_export_response_markdown(self, mock_db_session, mock_site):
        """Test creating Markdown export response."""
        response = await Exporter.create_export_response(
            db=mock_db_session,
            site_id=1,
            site=mock_site,
            format="md",
            include_content=True,
            stream_large=False
        )
        
        assert response.media_type == "text/markdown"
        assert "Content-Disposition" in response.headers