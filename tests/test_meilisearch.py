"""
Unit tests for Meilisearch search engine - with mocked HTTP client
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, patch, MagicMock
from app.meilisearch_engine import MeiliSearchEngine


@pytest.fixture
def mock_meilisearch_client():
    """Create a mocked Meilisearch client"""
    with patch('app.meilisearch_engine.meilisearch.Client') as MockClient:
        # Create mock client and index
        mock_client = Mock()
        mock_index = Mock()
        
        # Configure mock client
        MockClient.return_value = mock_client
        mock_client.index.return_value = mock_index
        mock_client.health.return_value = {"status": "available"}
        
        # Configure mock index for update_settings
        mock_index.update_settings.return_value = {"taskUid": 1}
        
        yield mock_client, mock_index


class TestMeiliSearchEngineInit:
    """Test MeiliSearchEngine initialization"""
    
    def test_engine_initialization(self, mock_meilisearch_client):
        """Test that engine initializes with correct settings"""
        mock_client, mock_index = mock_meilisearch_client
        
        engine = MeiliSearchEngine(index_name="test_pages")
        
        # Verify client was created
        assert engine.client == mock_client
        assert engine.index_name == "test_pages"
        assert engine.index == mock_index
        
        # Verify index was retrieved
        mock_client.index.assert_called_once_with("test_pages")
    
    def test_default_index_name(self, mock_meilisearch_client):
        """Test default index name"""
        mock_client, mock_index = mock_meilisearch_client
        
        engine = MeiliSearchEngine()
        
        assert engine.index_name == "pages"
        mock_client.index.assert_called_once_with("pages")
    
    def test_index_configuration(self, mock_meilisearch_client):
        """Test that index settings are configured on init"""
        mock_client, mock_index = mock_meilisearch_client
        
        engine = MeiliSearchEngine()
        
        # Verify update_settings was called
        mock_index.update_settings.assert_called_once()
        
        # Get the settings that were passed
        call_args = mock_index.update_settings.call_args
        settings = call_args[0][0]
        
        # Verify searchable attributes
        assert "searchableAttributes" in settings
        assert settings["searchableAttributes"] == ["title", "content", "url"]
        
        # Verify typo tolerance settings
        assert "typoTolerance" in settings
        assert settings["typoTolerance"]["enabled"] is True
        assert settings["typoTolerance"]["minWordSizeForTypos"]["oneTypo"] == 4
        assert settings["typoTolerance"]["minWordSizeForTypos"]["twoTypos"] == 8
        
        # Verify filterable attributes
        assert "filterableAttributes" in settings
        assert "site_id" in settings["filterableAttributes"]


class TestMeiliSearchEngineIndexing:
    """Test indexing pages in Meilisearch"""
    
    @pytest.mark.asyncio
    async def test_index_pages(self, mock_meilisearch_client):
        """Test indexing multiple pages"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock add_documents response
        mock_task = Mock()
        mock_task.task_uid = 123
        mock_index.add_documents.return_value = mock_task
        
        engine = MeiliSearchEngine()
        
        pages = [
            {
                "id": 1,
                "site_id": 10,
                "url": "https://example.com/page1",
                "title": "Test Page 1",
                "content": "This is test content for page 1",
                "metadata": {"word_count": 7},
                "indexed_at": "2024-01-01T00:00:00"
            },
            {
                "id": 2,
                "site_id": 10,
                "url": "https://example.com/page2",
                "title": "Test Page 2",
                "content": "This is test content for page 2",
                "metadata": {"word_count": 7},
                "indexed_at": "2024-01-01T00:01:00"
            }
        ]
        
        result = await engine.index_pages(pages)
        
        # Verify result
        assert result["task_uid"] == 123
        assert result["indexed"] == 2
        
        # Verify add_documents was called
        mock_index.add_documents.assert_called_once()
        
        # Get the documents that were indexed
        call_args = mock_index.add_documents.call_args
        documents = call_args[0][0]
        
        assert len(documents) == 2
        assert documents[0]["id"] == "10_1"  # Composite ID
        assert documents[0]["site_id"] == 10
        assert documents[0]["title"] == "Test Page 1"
        assert documents[1]["id"] == "10_2"
    
    @pytest.mark.asyncio
    async def test_index_empty_pages(self, mock_meilisearch_client):
        """Test indexing with empty page list"""
        mock_client, mock_index = mock_meilisearch_client
        
        engine = MeiliSearchEngine()
        
        result = await engine.index_pages([])
        
        # Should return without calling add_documents
        assert result["task_uid"] is None
        assert result["indexed"] == 0
        mock_index.add_documents.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_index_pages_content_truncation(self, mock_meilisearch_client):
        """Test that content is truncated to 10k chars"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_task = Mock()
        mock_task.task_uid = 456
        mock_index.add_documents.return_value = mock_task
        
        engine = MeiliSearchEngine()
        
        # Create page with very long content
        long_content = "a" * 15000
        pages = [
            {
                "id": 1,
                "site_id": 10,
                "url": "https://example.com/long",
                "title": "Long Page",
                "content": long_content,
                "metadata": {}
            }
        ]
        
        await engine.index_pages(pages)
        
        # Get indexed document
        call_args = mock_index.add_documents.call_args
        documents = call_args[0][0]
        
        # Verify content was truncated
        assert len(documents[0]["content"]) == 10000


class TestMeiliSearchEngineSearch:
    """Test search functionality"""
    
    @pytest.mark.asyncio
    async def test_search_basic(self, mock_meilisearch_client):
        """Test basic search query"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock search response
        mock_search_results = {
            "hits": [
                {
                    "id": "10_1",
                    "site_id": 10,
                    "url": "https://example.com/page1",
                    "title": "Python Tutorial",
                    "content": "Learn Python programming",
                    "_formatted": {
                        "title": "<mark>Python</mark> Tutorial",
                        "content": "Learn <mark>Python</mark> programming"
                    },
                    "_rankingScore": 0.95
                }
            ],
            "estimatedTotalHits": 1,
            "processingTimeMs": 5
        }
        mock_index.search.return_value = mock_search_results
        
        engine = MeiliSearchEngine()
        
        results = await engine.search("python", limit=20)
        
        # Verify search was called
        mock_index.search.assert_called_once()
        call_args = mock_index.search.call_args
        assert call_args[0][0] == "python"
        
        # Verify search options
        options = call_args[0][1]
        assert options["limit"] == 20
        assert options["offset"] == 0
        assert options["filter"] is None
        assert options["attributesToHighlight"] == ["title", "content"]
        assert options["highlightPreTag"] == "<mark>"
        assert options["highlightPostTag"] == "</mark>"
        
        # Verify results
        assert results["query"] == "python"
        assert results["total_hits"] == 1
        assert results["processing_time_ms"] == 5
        assert len(results["hits"]) == 1
        
        hit = results["hits"][0]
        assert hit["id"] == "10_1"
        assert hit["url"] == "https://example.com/page1"
        assert "<mark>" in hit["title"]
        assert "<mark>" in hit["snippet"]
    
    @pytest.mark.asyncio
    async def test_search_with_site_filter(self, mock_meilisearch_client):
        """Test search with site_id filter"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_search_results = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 2
        }
        mock_index.search.return_value = mock_search_results
        
        engine = MeiliSearchEngine()
        
        await engine.search("test", site_id=42, limit=10)
        
        # Verify filter was applied
        call_args = mock_index.search.call_args
        options = call_args[0][1]
        assert options["filter"] == "site_id = 42"
    
    @pytest.mark.asyncio
    async def test_search_pagination(self, mock_meilisearch_client):
        """Test search with pagination"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_search_results = {
            "hits": [],
            "estimatedTotalHits": 100,
            "processingTimeMs": 3
        }
        mock_index.search.return_value = mock_search_results
        
        engine = MeiliSearchEngine()
        
        await engine.search("query", limit=50, offset=20)
        
        # Verify pagination parameters
        call_args = mock_index.search.call_args
        options = call_args[0][1]
        assert options["limit"] == 50
        assert options["offset"] == 20
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, mock_meilisearch_client):
        """Test search with no results"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_search_results = {
            "hits": [],
            "estimatedTotalHits": 0,
            "processingTimeMs": 1
        }
        mock_index.search.return_value = mock_search_results
        
        engine = MeiliSearchEngine()
        
        results = await engine.search("nonexistent")
        
        assert results["query"] == "nonexistent"
        assert results["total_hits"] == 0
        assert results["hits"] == []


class TestMeiliSearchEngineDeletion:
    """Test deletion operations"""
    
    @pytest.mark.asyncio
    async def test_delete_site_pages(self, mock_meilisearch_client):
        """Test deleting all pages for a site"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock delete response
        mock_task = Mock()
        mock_task.task_uid = 789
        mock_index.delete_documents_by_filter = Mock(return_value=mock_task)
        
        engine = MeiliSearchEngine()
        
        result = await engine.delete_site_pages(site_id=42)
        
        # Verify delete was called with correct filter
        mock_index.delete_documents_by_filter.assert_called_once_with("site_id = 42")
        
        assert result["task_uid"] == 789
        assert result["status"] == "pending"
    
    @pytest.mark.asyncio
    async def test_delete_site_pages_error(self, mock_meilisearch_client):
        """Test error handling in delete_site_pages"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock delete to raise exception
        mock_index.delete_documents_by_filter = Mock(side_effect=Exception("Delete failed"))
        
        engine = MeiliSearchEngine()
        
        result = await engine.delete_site_pages(site_id=42)
        
        # Should return error status
        assert result["task_uid"] is None
        assert result["status"] == "error"
        assert "Delete failed" in result["error"]
    
    @pytest.mark.asyncio
    async def test_delete_pages(self, mock_meilisearch_client):
        """Test deleting specific pages by ID"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_task = Mock()
        mock_task.task_uid = 999
        mock_index.delete_documents.return_value = mock_task
        
        engine = MeiliSearchEngine()
        
        page_ids = ["10_1", "10_2", "10_3"]
        result = await engine.delete_pages(page_ids)
        
        # Verify delete was called
        mock_index.delete_documents.assert_called_once_with(page_ids)
        
        assert result["task_uid"] == 999
        assert result["deleted"] == 3
    
    @pytest.mark.asyncio
    async def test_delete_pages_empty_list(self, mock_meilisearch_client):
        """Test deleting with empty page list"""
        mock_client, mock_index = mock_meilisearch_client
        
        engine = MeiliSearchEngine()
        
        result = await engine.delete_pages([])
        
        # Should not call delete
        mock_index.delete_documents.assert_not_called()
        assert result["task_uid"] is None
        assert result["deleted"] == 0
    
    @pytest.mark.asyncio
    async def test_clear_index(self, mock_meilisearch_client):
        """Test clearing all documents from index"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_task = Mock()
        mock_task.task_uid = 111
        mock_index.delete_all_documents.return_value = mock_task
        
        engine = MeiliSearchEngine()
        
        result = await engine.clear_index()
        
        # Verify delete_all was called
        mock_index.delete_all_documents.assert_called_once()
        
        assert result["task_uid"] == 111
        assert result["status"] == "pending"


class TestMeiliSearchEngineStats:
    """Test statistics and health check"""
    
    @pytest.mark.asyncio
    async def test_get_stats(self, mock_meilisearch_client):
        """Test getting index statistics"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock stats response
        mock_stats = {
            "numberOfDocuments": 150,
            "isIndexing": False,
            "fieldDistribution": {
                "title": 150,
                "content": 148,
                "url": 150
            }
        }
        mock_index.get_stats.return_value = mock_stats
        
        engine = MeiliSearchEngine()
        
        stats = await engine.get_stats()
        
        # Verify stats
        assert stats["total_documents"] == 150
        assert stats["is_indexing"] is False
        assert "title" in stats["field_distribution"]
        assert stats["field_distribution"]["title"] == 150
    
    @pytest.mark.asyncio
    async def test_get_stats_error(self, mock_meilisearch_client):
        """Test get_stats error handling"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock error
        mock_index.get_stats.side_effect = Exception("Stats unavailable")
        
        engine = MeiliSearchEngine()
        
        stats = await engine.get_stats()
        
        # Should return default values with error
        assert stats["total_documents"] == 0
        assert stats["is_indexing"] is False
        assert "error" in stats
    
    def test_health_check_success(self, mock_meilisearch_client):
        """Test health check when Meilisearch is available"""
        mock_client, mock_index = mock_meilisearch_client
        
        mock_client.health.return_value = {"status": "available"}
        
        engine = MeiliSearchEngine()
        
        is_healthy = engine.health_check()
        
        assert is_healthy is True
        mock_client.health.assert_called_once()
    
    def test_health_check_failure(self, mock_meilisearch_client):
        """Test health check when Meilisearch is unavailable"""
        mock_client, mock_index = mock_meilisearch_client
        
        # Mock health check to raise exception
        mock_client.health.side_effect = Exception("Connection refused")
        
        engine = MeiliSearchEngine()
        
        is_healthy = engine.health_check()
        
        assert is_healthy is False
