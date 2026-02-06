"""
Meilisearch search engine integration for fast, typo-tolerant search.
"""

import meilisearch
from typing import List, Dict, Optional
from app.config import get_settings

settings = get_settings()


class MeiliSearchEngine:
    """Meilisearch implementation for fast, fuzzy search with typo tolerance."""
    
    def __init__(self, index_name: str = "pages"):
        """
        Initialize Meilisearch client and configure index.
        
        Args:
            index_name: Name of the Meilisearch index to use
        """
        self.client = meilisearch.Client(
            settings.meilisearch_host,
            settings.meili_master_key
        )
        self.index_name = index_name
        self.index = self.client.index(index_name)
        self._ensure_index_config()
    
    def _ensure_index_config(self):
        """
        Configure index settings for optimal search performance.
        
        Settings include:
        - Searchable attributes: title, content, url
        - Typo tolerance: 1 typo at 4 chars, 2 typos at 8 chars
        - Custom ranking rules for relevance
        - Highlighting with <mark> tags
        - Content cropping at 200 characters
        """
        try:
            self.index.update_settings({
                "searchableAttributes": [
                    "title",
                    "content",
                    "url"
                ],
                "displayedAttributes": [
                    "id",
                    "site_id",
                    "url",
                    "title",
                    "content",
                    "metadata"
                ],
                "rankingRules": [
                    "words",
                    "typo",
                    "proximity",
                    "attribute",
                    "sort",
                    "exactness"
                ],
                "typoTolerance": {
                    "enabled": True,
                    "minWordSizeForTypos": {
                        "oneTypo": 4,
                        "twoTypos": 8
                    }
                },
                "filterableAttributes": [
                    "site_id"
                ],
                "sortableAttributes": [
                    "indexed_at"
                ]
            })
        except Exception as e:
            # Log but don't fail if index already configured
            if settings.debug:
                print(f"Index configuration warning: {e}")
    
    async def index_pages(self, pages: List[Dict]) -> Dict:
        """
        Index multiple pages in Meilisearch.
        
        Args:
            pages: List of page dictionaries with keys: id, site_id, url, title, content, metadata
            
        Returns:
            Dict with task_uid for tracking indexing status
        """
        if not pages:
            return {"task_uid": None, "indexed": 0}
        
        documents = [
            {
                "id": f"{page['site_id']}_{page['id']}",  # Composite ID for uniqueness
                "site_id": page["site_id"],
                "url": page["url"],
                "title": page.get("title", ""),
                "content": page.get("content", "")[:10000],  # Limit content size to 10k chars
                "metadata": page.get("metadata", {}),
                "indexed_at": page.get("indexed_at")
            }
            for page in pages
        ]
        
        task = self.index.add_documents(documents)
        return {
            "task_uid": task.task_uid,
            "indexed": len(documents)
        }
    
    async def search(
        self,
        query: str,
        site_id: Optional[int] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Search pages with Meilisearch using typo-tolerant fuzzy matching.
        
        Args:
            query: Search query string
            site_id: Optional site ID to filter results
            limit: Maximum number of results to return (default: 20)
            offset: Pagination offset (default: 0)
            
        Returns:
            Dict with search results including:
            - query: Original search query
            - total_hits: Estimated total number of matching documents
            - hits: List of matching pages with highlights
            - processing_time_ms: Time taken to process the search
        """
        # Build filter expression
        filter_expr = None
        if site_id is not None:
            filter_expr = f"site_id = {site_id}"
        
        # Execute search with highlighting and cropping
        results = self.index.search(
            query,
            {
                "limit": limit,
                "offset": offset,
                "filter": filter_expr,
                "attributesToHighlight": ["title", "content"],
                "attributesToCrop": ["content"],
                "cropLength": 200,
                "highlightPreTag": "<mark>",
                "highlightPostTag": "</mark>"
            }
        )
        
        # Transform results into consistent format
        return {
            "query": query,
            "total_hits": results.get("estimatedTotalHits", 0),
            "hits": [
                {
                    "id": hit["id"],
                    "site_id": hit["site_id"],
                    "url": hit["url"],
                    "title": hit.get("_formatted", {}).get("title", hit.get("title", "")),
                    "snippet": hit.get("_formatted", {}).get("content", hit.get("content", ""))[:200],
                    "rank": hit.get("_rankingScore", 0.0)
                }
                for hit in results.get("hits", [])
            ],
            "processing_time_ms": results.get("processingTimeMs", 0)
        }
    
    async def delete_site_pages(self, site_id: int) -> Dict:
        """
        Delete all pages for a specific site from the index.
        
        Args:
            site_id: The site ID whose pages should be deleted
            
        Returns:
            Dict with task_uid for tracking deletion status
        """
        try:
            task = self.index.delete_documents_by_filter(f"site_id = {site_id}")
            return {
                "task_uid": task.task_uid,
                "status": "pending"
            }
        except Exception as e:
            if settings.debug:
                print(f"Error deleting site pages: {e}")
            return {
                "task_uid": None,
                "status": "error",
                "error": str(e)
            }
    
    async def delete_pages(self, page_ids: List[str]) -> Dict:
        """
        Delete specific pages from the index by their IDs.
        
        Args:
            page_ids: List of page IDs to delete (composite format: "site_id_page_id")
            
        Returns:
            Dict with task_uid for tracking deletion status
        """
        if not page_ids:
            return {"task_uid": None, "deleted": 0}
        
        task = self.index.delete_documents(page_ids)
        return {
            "task_uid": task.task_uid,
            "deleted": len(page_ids)
        }
    
    async def get_stats(self) -> Dict:
        """
        Get statistics about the search index.
        
        Returns:
            Dict with index statistics including document count
        """
        try:
            stats = self.index.get_stats()
            return {
                "total_documents": stats.get("numberOfDocuments", 0),
                "is_indexing": stats.get("isIndexing", False),
                "field_distribution": stats.get("fieldDistribution", {})
            }
        except Exception as e:
            if settings.debug:
                print(f"Error getting index stats: {e}")
            return {
                "total_documents": 0,
                "is_indexing": False,
                "error": str(e)
            }
    
    async def clear_index(self) -> Dict:
        """
        Clear all documents from the index.
        
        WARNING: This deletes all indexed pages.
        
        Returns:
            Dict with task_uid for tracking deletion status
        """
        task = self.index.delete_all_documents()
        return {
            "task_uid": task.task_uid,
            "status": "pending"
        }
    
    def health_check(self) -> bool:
        """
        Check if Meilisearch is accessible and healthy.
        
        Returns:
            True if Meilisearch is accessible, False otherwise
        """
        try:
            self.client.health()
            return True
        except Exception:
            return False
