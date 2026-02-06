"""
Search engine using SQLite FTS5
"""

import sqlite3
from typing import List, Dict, Any, Optional, Union


class SearchEngine:
    """Full-text search using SQLite FTS5"""
    
    def __init__(self, db_path: str = "indexer.db"):
        """Initialize search engine with database path"""
        self.db_path = db_path
    
    def search(
        self, 
        query: str, 
        site_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search pages with FTS5
        
        Args:
            query: Search query
            site_id: Optional site ID to filter results
            limit: Maximum number of results
            
        Returns:
            List of search results with snippets and highlights
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build query with optional site filter
        # Note: snippet() column index is 0-based: 0=title, 1=content
        # We use -1 to match across all columns
        sql = """
            SELECT 
                p.id,
                p.site_id,
                p.url,
                p.title,
                snippet(pages_fts, -1, '<mark>', '</mark>', '...', 30) as snippet,
                rank
            FROM pages_fts
            JOIN pages p ON pages_fts.rowid = p.id
            WHERE pages_fts MATCH ?
        """
        params: List[Union[str, int]] = [query]
        
        if site_id:
            sql += " AND p.site_id = ?"
            params.append(site_id)
        
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row['id'],
                'site_id': row['site_id'],
                'url': row['url'],
                'title': row['title'],
                'snippet': row['snippet'],
                'rank': row['rank']
            })
        
        conn.close()
        return results
