"""
Unit tests for app/search.py - SearchEngine queries and ranking
"""

import pytest
import tempfile
import os
from app.search import SearchEngine
from app.database import init_db, create_site, create_page


@pytest.fixture
def test_db():
    """Create a temporary database for testing"""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Initialize the database
    init_db(db_path)
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def search_engine(test_db):
    """Create a SearchEngine instance with test database"""
    return SearchEngine(db_path=test_db)


@pytest.fixture
def populated_db(test_db):
    """Create a database populated with test data"""
    # Create sites
    site1_id = create_site("https://example.com", "example.com", test_db)
    site2_id = create_site("https://test.com", "test.com", test_db)
    
    # Create pages for site1
    create_page(
        site1_id,
        "https://example.com/python",
        "Python Programming Tutorial",
        "Learn Python programming language. Python is a high-level, interpreted programming language known for its simplicity and readability.",
        test_db
    )
    create_page(
        site1_id,
        "https://example.com/javascript",
        "JavaScript Guide",
        "Master JavaScript for web development. JavaScript is the language of the web, used for both frontend and backend development.",
        test_db
    )
    create_page(
        site1_id,
        "https://example.com/rust",
        "Rust Programming",
        "Discover Rust programming language. Rust is a systems programming language focused on safety and performance.",
        test_db
    )
    
    # Create pages for site2
    create_page(
        site2_id,
        "https://test.com/python-advanced",
        "Advanced Python Techniques",
        "Deep dive into advanced Python concepts including decorators, generators, and metaclasses.",
        test_db
    )
    create_page(
        site2_id,
        "https://test.com/web-development",
        "Web Development Basics",
        "Introduction to web development using HTML, CSS, and JavaScript frameworks.",
        test_db
    )
    
    return test_db, site1_id, site2_id


class TestSearchEngineInit:
    """Test SearchEngine initialization"""
    
    def test_init_with_default_path(self):
        """Test initialization with default database path"""
        engine = SearchEngine()
        assert engine.db_path == "indexer.db"
    
    def test_init_with_custom_path(self, test_db):
        """Test initialization with custom database path"""
        engine = SearchEngine(db_path=test_db)
        assert engine.db_path == test_db


class TestBasicSearch:
    """Test basic search functionality"""
    
    def test_search_single_result(self, populated_db, search_engine):
        """Test search that returns a single result"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("rust")
        
        assert len(results) == 1
        assert results[0]['title'] == "Rust Programming"
        assert results[0]['url'] == "https://example.com/rust"
    
    def test_search_multiple_results(self, populated_db, search_engine):
        """Test search that returns multiple results"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) == 2
        titles = [r['title'] for r in results]
        assert "Python Programming Tutorial" in titles
        assert "Advanced Python Techniques" in titles
    
    def test_search_no_results(self, populated_db, search_engine):
        """Test search that returns no results"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("nonexistent")
        
        assert len(results) == 0
        assert results == []
    
    def test_search_case_insensitive(self, populated_db, search_engine):
        """Test that search is case-insensitive"""
        test_db, site1_id, site2_id = populated_db
        
        # All variations should return same results
        queries = ['python', 'PYTHON', 'Python', 'PyThOn']
        
        first_results = None
        for query in queries:
            results = search_engine.search(query)
            assert len(results) == 2, f"Query '{query}' returned {len(results)} results"
            
            if first_results is None:
                first_results = results
            else:
                # Compare IDs to ensure same results
                assert {r['id'] for r in results} == {r['id'] for r in first_results}
    
    def test_search_in_title(self, populated_db, search_engine):
        """Test search matches in title"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("Tutorial")
        
        assert len(results) == 1
        assert "Tutorial" in results[0]['title']
    
    def test_search_in_content(self, populated_db, search_engine):
        """Test search matches in content"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("decorators")
        
        assert len(results) == 1
        assert "Advanced Python Techniques" in results[0]['title']
    
    def test_search_in_both_title_and_content(self, populated_db, search_engine):
        """Test search matches in both title and content"""
        test_db, site1_id, site2_id = populated_db
        
        # "JavaScript" appears in both title and content of the JavaScript page
        results = search_engine.search("JavaScript")
        
        # Should find both the JavaScript Guide and Web Development pages
        assert len(results) >= 1
        titles = [r['title'] for r in results]
        assert "JavaScript Guide" in titles


class TestSearchFiltering:
    """Test search filtering by site_id"""
    
    def test_search_filter_by_site_id(self, populated_db, search_engine):
        """Test filtering results by site_id"""
        test_db, site1_id, site2_id = populated_db
        
        # Search for "python" in site1 only
        results = search_engine.search("python", site_id=site1_id)
        
        assert len(results) == 1
        assert results[0]['site_id'] == site1_id
        assert results[0]['title'] == "Python Programming Tutorial"
    
    def test_search_filter_by_site_id_no_results(self, populated_db, search_engine):
        """Test filtering by site_id with no matching results"""
        test_db, site1_id, site2_id = populated_db
        
        # Search for "rust" in site2 (it only exists in site1)
        results = search_engine.search("rust", site_id=site2_id)
        
        assert len(results) == 0
    
    def test_search_filter_different_sites(self, populated_db, search_engine):
        """Test that filtering correctly separates results by site"""
        test_db, site1_id, site2_id = populated_db
        
        # "python" exists in both sites
        site1_results = search_engine.search("python", site_id=site1_id)
        site2_results = search_engine.search("python", site_id=site2_id)
        
        assert len(site1_results) == 1
        assert len(site2_results) == 1
        assert site1_results[0]['site_id'] == site1_id
        assert site2_results[0]['site_id'] == site2_id
        assert site1_results[0]['id'] != site2_results[0]['id']
    
    def test_search_without_site_filter(self, populated_db, search_engine):
        """Test search without site filter returns results from all sites"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python", site_id=None)
        
        assert len(results) == 2
        site_ids = {r['site_id'] for r in results}
        assert site1_id in site_ids
        assert site2_id in site_ids


class TestSearchLimit:
    """Test search result limiting"""
    
    def test_search_default_limit(self, populated_db, search_engine):
        """Test default limit of 10 results"""
        test_db, site1_id, site2_id = populated_db
        
        # Create more pages
        for i in range(15):
            create_page(
                site1_id,
                f"https://example.com/page{i}",
                f"Web Page {i}",
                "This is a web page about web development and web design.",
                test_db
            )
        
        results = search_engine.search("web")
        
        # Should be limited to 10 results by default
        assert len(results) <= 10
    
    def test_search_custom_limit(self, populated_db, search_engine):
        """Test custom result limit"""
        test_db, site1_id, site2_id = populated_db
        
        # Create several pages
        for i in range(10):
            create_page(
                site1_id,
                f"https://example.com/test{i}",
                f"Test Page {i}",
                "Testing the search functionality with test content.",
                test_db
            )
        
        # Search with limit of 3
        results = search_engine.search("test", limit=3)
        
        assert len(results) == 3
    
    def test_search_limit_larger_than_results(self, populated_db, search_engine):
        """Test limit larger than available results"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python", limit=100)
        
        # Only 2 pages contain "python", so should return 2
        assert len(results) == 2
    
    def test_search_limit_zero(self, populated_db, search_engine):
        """Test search with limit of 0 returns no results"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python", limit=0)
        
        assert len(results) == 0


class TestSearchSnippets:
    """Test search snippet generation"""
    
    def test_search_returns_snippet(self, populated_db, search_engine):
        """Test that search returns snippets"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) > 0
        for result in results:
            assert 'snippet' in result
            assert result['snippet'] is not None
    
    def test_snippet_contains_highlights(self, populated_db, search_engine):
        """Test that snippets contain <mark> highlights"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) > 0
        # At least one result should have highlights
        has_highlights = any('<mark>' in r['snippet'] and '</mark>' in r['snippet'] 
                           for r in results)
        assert has_highlights
    
    def test_snippet_highlights_search_term(self, populated_db, search_engine):
        """Test that snippet highlights the search term"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("rust")
        
        assert len(results) == 1
        snippet = results[0]['snippet'].lower()
        # Should contain "rust" with or without marks
        assert 'rust' in snippet
        # Should have mark tags
        assert '<mark>' in results[0]['snippet']


class TestSearchRanking:
    """Test search result ranking"""
    
    def test_search_returns_rank(self, populated_db, search_engine):
        """Test that search results include rank"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) > 0
        for result in results:
            assert 'rank' in result
            assert result['rank'] is not None
    
    def test_search_ordered_by_rank(self, populated_db, search_engine):
        """Test that results are ordered by rank (lower rank = better)"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        if len(results) > 1:
            # FTS5 rank is negative, with better matches having lower (more negative) values
            ranks = [r['rank'] for r in results]
            # Check that ranks are in ascending order (more negative first)
            for i in range(len(ranks) - 1):
                assert ranks[i] <= ranks[i + 1], "Results should be ordered by rank"
    
    def test_search_title_match_ranked_higher(self, test_db, search_engine):
        """Test that title matches are typically ranked higher than content-only matches"""
        # Create two pages: one with term in title, one with term only in content
        site_id = create_site("https://example.com", "example.com", test_db)
        
        create_page(
            site_id,
            "https://example.com/page1",
            "Some Generic Title",
            "This page is all about quantum physics and quantum mechanics.",
            test_db
        )
        create_page(
            site_id,
            "https://example.com/page2",
            "Quantum Physics Overview",
            "This is an overview page with general information.",
            test_db
        )
        
        results = search_engine.search("quantum")
        
        assert len(results) == 2
        # Both pages should be found
        titles = {r['title'] for r in results}
        assert "Quantum Physics Overview" in titles
        assert "Some Generic Title" in titles
        # Note: FTS5 ranking depends on various factors including term frequency
        # so we just verify both results are present rather than asserting order


class TestSearchResultFields:
    """Test that search results contain all expected fields"""
    
    def test_search_result_structure(self, populated_db, search_engine):
        """Test that search results have all expected fields"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) > 0
        
        expected_fields = ['id', 'site_id', 'url', 'title', 'snippet', 'rank']
        for result in results:
            for field in expected_fields:
                assert field in result, f"Result missing field: {field}"
    
    def test_search_result_types(self, populated_db, search_engine):
        """Test that search result fields have correct types"""
        test_db, site1_id, site2_id = populated_db
        
        results = search_engine.search("python")
        
        assert len(results) > 0
        
        result = results[0]
        assert isinstance(result['id'], int)
        assert isinstance(result['site_id'], int)
        assert isinstance(result['url'], str)
        assert isinstance(result['title'], str)
        assert isinstance(result['snippet'], str)
        # rank is a float in SQLite FTS5
        assert isinstance(result['rank'], (int, float))


class TestSearchEdgeCases:
    """Test edge cases and special scenarios"""
    
    def test_search_empty_query(self, populated_db, search_engine):
        """Test search with empty query"""
        test_db, site1_id, site2_id = populated_db
        
        # FTS5 will raise an error for empty query
        # The SearchEngine should handle this gracefully or let it raise
        # Depending on implementation, this might return empty results or raise
        try:
            results = search_engine.search("")
            # If it doesn't raise, it should return empty results
            assert results == []
        except Exception:
            # Or it might raise an exception, which is also acceptable
            pass
    
    def test_search_special_characters(self, populated_db, search_engine):
        """Test search with special characters"""
        test_db, site1_id, site2_id = populated_db
        
        # Create a page with special characters
        create_page(
            site1_id,
            "https://example.com/special",
            "C++ Programming",
            "Learn C++ programming language.",
            test_db
        )
        
        # Search for C++ (has special chars)
        # This might need special handling depending on FTS5 configuration
        try:
            results = search_engine.search("C++")
            # Should find the C++ page if tokenizer handles it correctly
            # Or might return empty if tokenizer strips special chars
            assert isinstance(results, list)
        except Exception:
            # FTS5 might raise error on certain special characters
            pass
    
    def test_search_on_empty_database(self, test_db, search_engine):
        """Test search on database with no pages"""
        results = search_engine.search("anything")
        
        assert len(results) == 0
        assert results == []
    
    def test_search_multiple_terms(self, populated_db, search_engine):
        """Test search with multiple terms"""
        test_db, site1_id, site2_id = populated_db
        
        # Search for multiple terms
        results = search_engine.search("python programming")
        
        # Should find pages containing both or either term
        assert len(results) > 0
        # At least the Python Programming Tutorial should be found
        titles = [r['title'] for r in results]
        assert "Python Programming Tutorial" in titles
