"""
Unit tests for app/database.py - CRUD operations and FTS5 search
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from app.database import (
    init_db,
    get_db_connection,
    create_site,
    get_site,
    get_site_by_domain,
    create_page,
    get_pages_for_site,
    update_site_status,
    get_all_sites
)


@pytest.fixture
def test_db():
    """Create a temporary database for testing"""
    # Create a temporary file
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    # Initialize the database
    init_db(db_path)
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestDatabaseInit:
    """Test database initialization"""
    
    def test_init_db_creates_tables(self, test_db):
        """Test that init_db creates all required tables"""
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        
        # Check sites table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sites'")
        assert cursor.fetchone() is not None
        
        # Check pages table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages'")
        assert cursor.fetchone() is not None
        
        # Check FTS5 virtual table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages_fts'")
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_init_db_creates_indexes(self, test_db):
        """Test that init_db creates all required indexes"""
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        
        # Check indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pages_site_id'")
        assert cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sites_domain'")
        assert cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sites_status'")
        assert cursor.fetchone() is not None
        
        conn.close()
    
    def test_init_db_creates_triggers(self, test_db):
        """Test that init_db creates FTS triggers"""
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        
        # Check triggers exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='pages_ai'")
        assert cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='pages_ad'")
        assert cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='pages_au'")
        assert cursor.fetchone() is not None
        
        conn.close()


class TestSiteOperations:
    """Test site CRUD operations"""
    
    def test_create_site(self, test_db):
        """Test creating a new site"""
        site_id = create_site("https://example.com", "example.com", test_db)
        assert site_id > 0
        
        # Verify site was created
        site = get_site(site_id, test_db)
        assert site is not None
        assert site['url'] == "https://example.com"
        assert site['domain'] == "example.com"
        assert site['status'] == "pending"
        assert site['page_count'] == 0
    
    def test_create_site_duplicate_domain(self, test_db):
        """Test creating a site with duplicate domain fails"""
        create_site("https://example.com", "example.com", test_db)
        
        # Attempting to create another site with same domain should raise exception
        with pytest.raises(sqlite3.IntegrityError):
            create_site("https://example.com/other", "example.com", test_db)
    
    def test_get_site(self, test_db):
        """Test getting a site by ID"""
        site_id = create_site("https://example.com", "example.com", test_db)
        site = get_site(site_id, test_db)
        
        assert site is not None
        assert site['id'] == site_id
        assert site['domain'] == "example.com"
    
    def test_get_site_not_found(self, test_db):
        """Test getting a non-existent site returns None"""
        site = get_site(999, test_db)
        assert site is None
    
    def test_get_site_by_domain(self, test_db):
        """Test getting a site by domain"""
        site_id = create_site("https://example.com", "example.com", test_db)
        site = get_site_by_domain("example.com", test_db)
        
        assert site is not None
        assert site['id'] == site_id
        assert site['domain'] == "example.com"
    
    def test_get_site_by_domain_not_found(self, test_db):
        """Test getting a non-existent domain returns None"""
        site = get_site_by_domain("nonexistent.com", test_db)
        assert site is None
    
    def test_update_site_status(self, test_db):
        """Test updating site status"""
        site_id = create_site("https://example.com", "example.com", test_db)
        
        # Update status only
        update_site_status(site_id, "scraping", db_path=test_db)
        site = get_site(site_id, test_db)
        assert site['status'] == "scraping"
        
        # Update status and page count
        update_site_status(site_id, "completed", page_count=42, db_path=test_db)
        site = get_site(site_id, test_db)
        assert site['status'] == "completed"
        assert site['page_count'] == 42
        assert site['last_scraped'] is not None
    
    def test_get_all_sites(self, test_db):
        """Test getting all sites"""
        # Create multiple sites
        create_site("https://example.com", "example.com", test_db)
        create_site("https://test.com", "test.com", test_db)
        create_site("https://demo.com", "demo.com", test_db)
        
        sites = get_all_sites(test_db)
        assert len(sites) == 3
        
        # Verify all domains are present
        domains = {site['domain'] for site in sites}
        assert domains == {"example.com", "test.com", "demo.com"}


class TestPageOperations:
    """Test page CRUD operations"""
    
    def test_create_page(self, test_db):
        """Test creating a new page"""
        site_id = create_site("https://example.com", "example.com", test_db)
        
        page_id = create_page(
            site_id=site_id,
            url="https://example.com/page1",
            title="Test Page",
            content="This is test content",
            db_path=test_db
        )
        
        assert page_id > 0
        
        # Verify page was created
        pages = get_pages_for_site(site_id, test_db)
        assert len(pages) == 1
        assert pages[0]['id'] == page_id
        assert pages[0]['url'] == "https://example.com/page1"
        assert pages[0]['title'] == "Test Page"
        assert pages[0]['content'] == "This is test content"
    
    def test_create_multiple_pages(self, test_db):
        """Test creating multiple pages for a site"""
        site_id = create_site("https://example.com", "example.com", test_db)
        
        page1_id = create_page(site_id, "https://example.com/page1", "Page 1", "Content 1", test_db)
        page2_id = create_page(site_id, "https://example.com/page2", "Page 2", "Content 2", test_db)
        page3_id = create_page(site_id, "https://example.com/page3", "Page 3", "Content 3", test_db)
        
        pages = get_pages_for_site(site_id, test_db)
        assert len(pages) == 3
        assert {p['id'] for p in pages} == {page1_id, page2_id, page3_id}
    
    def test_get_pages_for_site(self, test_db):
        """Test getting all pages for a site"""
        site1_id = create_site("https://example.com", "example.com", test_db)
        site2_id = create_site("https://test.com", "test.com", test_db)
        
        # Create pages for both sites
        create_page(site1_id, "https://example.com/page1", "Page 1", "Content 1", test_db)
        create_page(site1_id, "https://example.com/page2", "Page 2", "Content 2", test_db)
        create_page(site2_id, "https://test.com/page1", "Test Page", "Test Content", test_db)
        
        # Get pages for site1
        site1_pages = get_pages_for_site(site1_id, test_db)
        assert len(site1_pages) == 2
        assert all(p['site_id'] == site1_id for p in site1_pages)
        
        # Get pages for site2
        site2_pages = get_pages_for_site(site2_id, test_db)
        assert len(site2_pages) == 1
        assert site2_pages[0]['site_id'] == site2_id
    
    def test_get_pages_for_site_empty(self, test_db):
        """Test getting pages for a site with no pages"""
        site_id = create_site("https://example.com", "example.com", test_db)
        pages = get_pages_for_site(site_id, test_db)
        assert len(pages) == 0
        assert pages == []


class TestFTS5Search:
    """Test FTS5 full-text search functionality"""
    
    def test_fts_index_updated_on_insert(self, test_db):
        """Test that FTS5 index is updated when pages are inserted"""
        site_id = create_site("https://example.com", "example.com", test_db)
        create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn Python programming", test_db)
        
        # Query FTS index directly
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM pages_fts WHERE pages_fts MATCH 'python'")
        result = cursor.fetchone()
        conn.close()
        
        assert result['count'] == 1
    
    def test_fts_index_updated_on_delete(self, test_db):
        """Test that FTS5 index is updated when pages are deleted"""
        site_id = create_site("https://example.com", "example.com", test_db)
        page_id = create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn Python", test_db)
        
        # Delete the page
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        conn.commit()
        
        # Check FTS index is empty
        cursor.execute("SELECT COUNT(*) as count FROM pages_fts WHERE pages_fts MATCH 'python'")
        result = cursor.fetchone()
        conn.close()
        
        assert result['count'] == 0
    
    def test_fts_index_updated_on_update(self, test_db):
        """Test that FTS5 index is updated when pages are updated"""
        site_id = create_site("https://example.com", "example.com", test_db)
        page_id = create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn Python", test_db)
        
        # Update the page
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("UPDATE pages SET title = ?, content = ? WHERE id = ?", 
                      ("JavaScript Tutorial", "Learn JavaScript", page_id))
        conn.commit()
        
        # Old content should not be found
        cursor.execute("SELECT COUNT(*) as count FROM pages_fts WHERE pages_fts MATCH 'python'")
        result = cursor.fetchone()
        assert result['count'] == 0
        
        # New content should be found
        cursor.execute("SELECT COUNT(*) as count FROM pages_fts WHERE pages_fts MATCH 'javascript'")
        result = cursor.fetchone()
        conn.close()
        
        assert result['count'] == 1
    
    def test_fts_search_basic(self, test_db):
        """Test basic FTS5 search"""
        site_id = create_site("https://example.com", "example.com", test_db)
        create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn Python programming", test_db)
        create_page(site_id, "https://example.com/page2", "JavaScript Guide", "Learn JavaScript", test_db)
        
        # Search for "python"
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.title, p.content 
            FROM pages_fts 
            JOIN pages p ON pages_fts.rowid = p.id 
            WHERE pages_fts MATCH 'python'
        """)
        results = cursor.fetchall()
        conn.close()
        
        assert len(results) == 1
        assert results[0]['title'] == "Python Tutorial"
    
    def test_fts_search_multiple_results(self, test_db):
        """Test FTS5 search with multiple results"""
        site_id = create_site("https://example.com", "example.com", test_db)
        create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn Python programming", test_db)
        create_page(site_id, "https://example.com/page2", "Advanced Python", "Advanced Python concepts", test_db)
        create_page(site_id, "https://example.com/page3", "JavaScript Guide", "Learn JavaScript", test_db)
        
        # Search for "python"
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.title 
            FROM pages_fts 
            JOIN pages p ON pages_fts.rowid = p.id 
            WHERE pages_fts MATCH 'python'
        """)
        results = cursor.fetchall()
        conn.close()
        
        assert len(results) == 2
        titles = [r['title'] for r in results]
        assert "Python Tutorial" in titles
        assert "Advanced Python" in titles
    
    def test_fts_search_case_insensitive(self, test_db):
        """Test that FTS5 search is case-insensitive"""
        site_id = create_site("https://example.com", "example.com", test_db)
        create_page(site_id, "https://example.com/page1", "Python Tutorial", "Learn PYTHON programming", test_db)
        
        # Search with different cases
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        
        for query in ['python', 'PYTHON', 'Python', 'pYtHoN']:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM pages_fts 
                WHERE pages_fts MATCH ?
            """, (query,))
            result = cursor.fetchone()
            assert result['count'] == 1, f"Search for '{query}' failed"
        
        conn.close()
    
    def test_fts_search_snippet(self, test_db):
        """Test FTS5 snippet generation"""
        site_id = create_site("https://example.com", "example.com", test_db)
        create_page(
            site_id, 
            "https://example.com/page1", 
            "Python Tutorial", 
            "Python is a high-level programming language. Learn Python today!", 
            test_db
        )
        
        # Search with snippet
        conn = get_db_connection(test_db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT snippet(pages_fts, -1, '<mark>', '</mark>', '...', 30) as snippet
            FROM pages_fts 
            WHERE pages_fts MATCH 'python'
        """)
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        snippet = result['snippet']
        assert '<mark>' in snippet
        assert '</mark>' in snippet
        # Should highlight "python" in some form
        assert 'python' in snippet.lower()
