"""
Search analytics for the Site Search Platform.

Provides:
- Analytics class for aggregating search statistics
- Logging utilities for tracking search queries and results
- Dashboard generation for search analytics

Supports:
- Search query logging with results count, response time, and site ID
- Analytics dashboard with top queries, failed searches, and trends
- Time-based aggregation for search performance metrics
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import func, desc, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SearchQuery, Site


class Analytics:
    """
    Analytics engine for search query analysis.
    
    Provides methods for:
    - Logging search queries
    - Aggregating search statistics
    - Generating analytics dashboards
    """
    
    @staticmethod
    async def log_search_query(
        db: AsyncSession,
        query: str,
        results_count: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        site_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> SearchQuery:
        """
        Log a search query for analytics.
        
        Args:
            db: Database session
            query: Search query string
            results_count: Number of results found (optional)
            response_time_ms: Response time in milliseconds (optional)
            site_id: Site ID if query is site-specific (optional)
            ip_address: IP address of requester (optional)
            
        Returns:
            Logged SearchQuery object
        """
        search_query = SearchQuery(
            query=query,
            results_count=results_count,
            response_time_ms=response_time_ms,
            site_id=site_id,
            ip_address=ip_address
        )
        
        db.add(search_query)
        await db.commit()
        await db.refresh(search_query)
        
        return search_query
    
    @staticmethod
    async def get_search_stats(
        db: AsyncSession,
        site_id: Optional[int] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive search analytics for a given time period.
        
        Args:
            db: Database session
            site_id: Optional site ID to filter by
            days: Number of days to include in analysis (default: 30)
            
        Returns:
            Dictionary with analytics data:
            - period_days: Analysis period in days
            - total_searches: Total number of searches
            - unique_queries: Number of distinct search queries
            - top_queries: Top 20 most frequent queries
            - failed_searches: Number of searches with 0 results
            - avg_results_per_query: Average results per query
            - avg_response_time_ms: Average response time
            - searches_by_day: Daily search counts
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        # Base query for filtering by site and time
        base_conditions = [
            SearchQuery.timestamp >= since
        ]
        if site_id is not None:
            base_conditions.append(SearchQuery.site_id == site_id)
        
        # 1. Total searches
        total_query = select(func.count(SearchQuery.id)).where(*base_conditions)
        total_searches = await db.scalar(total_query) or 0
        
        # 2. Unique queries
        unique_query = select(func.count(func.distinct(SearchQuery.query))).where(*base_conditions)
        unique_queries = await db.scalar(unique_query) or 0
        
        # 3. Top queries (top 20)
        top_queries_result = await db.execute(
            select(
                SearchQuery.query,
                func.count(SearchQuery.id).label("count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time")
            )
            .where(*base_conditions)
            .group_by(SearchQuery.query)
            .order_by(desc("count"))
            .limit(20)
        )
        top_queries = []
        for row in top_queries_result:
            top_queries.append({
                "query": row.query,
                "count": row.count,
                "avg_results": round(float(row.avg_results or 0), 1),
                "avg_time_ms": round(float(row.avg_time or 0), 1)
            })
        
        # 4. Failed searches (0 results)
        failed_query = select(func.count(SearchQuery.id)).where(
            *base_conditions,
            SearchQuery.results_count == 0
        )
        failed_searches = await db.scalar(failed_query) or 0
        
        # 5. Average results per query (excluding failed searches)
        avg_results_query = select(func.avg(SearchQuery.results_count)).where(
            *base_conditions,
            SearchQuery.results_count > 0
        )
        avg_results_result = await db.scalar(avg_results_query)
        avg_results_per_query = round(float(avg_results_result or 0), 2)
        
        # 6. Average response time
        avg_time_query = select(func.avg(SearchQuery.response_time_ms)).where(*base_conditions)
        avg_response_time_result = await db.scalar(avg_time_query)
        avg_response_time_ms = round(float(avg_response_time_result or 0), 1)
        
        # 7. Searches by day
        searches_by_day = await Analytics._get_searches_by_day(db, site_id, since)
        
        # 8. Success rate
        success_rate = 0
        if total_searches > 0:
            success_rate = round((total_searches - failed_searches) / total_searches * 100, 1)
        
        # 9. Recent queries (last 24 hours)
        recent_24h = datetime.utcnow() - timedelta(hours=24)
        recent_query = select(func.count(SearchQuery.id)).where(
            *base_conditions,
            SearchQuery.timestamp >= recent_24h
        )
        recent_searches = await db.scalar(recent_query) or 0
        
        return {
            "period_days": days,
            "total_searches": total_searches,
            "unique_queries": unique_queries,
            "top_queries": top_queries,
            "failed_searches": failed_searches,
            "avg_results_per_query": avg_results_per_query,
            "avg_response_time_ms": avg_response_time_ms,
            "success_rate_percent": success_rate,
            "recent_searches_24h": recent_searches,
            "searches_by_day": searches_by_day,
        }
    
    @staticmethod
    async def _get_searches_by_day(
        db: AsyncSession,
        site_id: Optional[int],
        since: datetime
    ) -> List[Dict[str, Any]]:
        """
        Get daily search counts for time series visualization.
        
        Args:
            db: Database session
            site_id: Optional site ID to filter by
            since: Start date for analysis
            
        Returns:
            List of dictionaries with date and search count
        """
        # Try to detect database dialect for date truncation
        try:
            # PostgreSQL-style date truncation
            select_query = select(
                func.date_trunc('day', SearchQuery.timestamp).label("date"),
                func.count(SearchQuery.id).label("count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time")
            ).where(SearchQuery.timestamp >= since)
            
            if site_id is not None:
                select_query = select_query.where(SearchQuery.site_id == site_id)
            
            select_query = select_query.group_by(func.date_trunc('day', SearchQuery.timestamp)).order_by("date")
            
            result = await db.execute(select_query)
        except Exception:
            # SQLite-style date truncation using strftime
            select_query = select(
                func.strftime('%Y-%m-%d', SearchQuery.timestamp).label("date"),
                func.count(SearchQuery.id).label("count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time")
            ).where(SearchQuery.timestamp >= since)
            
            if site_id is not None:
                select_query = select_query.where(SearchQuery.site_id == site_id)
            
            select_query = select_query.group_by(func.strftime('%Y-%m-%d', SearchQuery.timestamp)).order_by("date")
            
            result = await db.execute(select_query)
        
        searches_by_day = []
        for row in result:
            searches_by_day.append({
                "date": row.date,
                "count": row.count,
                "avg_results": round(float(row.avg_results or 0), 1),
                "avg_time_ms": round(float(row.avg_time or 0), 1)
            })
        
        return searches_by_day
    
    @staticmethod
    async def get_site_comparison(
        db: AsyncSession,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Compare search activity across all sites.
        
        Args:
            db: Database session
            days: Number of days to include
            
        Returns:
            List of site comparison data
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        # Subquery for site search stats
        result = await db.execute(
            select(
                Site.id,
                Site.domain,
                func.count(SearchQuery.id).label("total_searches"),
                func.count(func.distinct(SearchQuery.query)).label("unique_queries"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time"),
                func.sum(case((SearchQuery.results_count == 0, 1), else_=0)).label("failed_searches")
            )
            .outerjoin(SearchQuery, SearchQuery.site_id == Site.id)
            .where(SearchQuery.timestamp >= since)
            .group_by(Site.id, Site.domain)
            .order_by(desc("total_searches"))
        )
        
        sites_comparison = []
        for row in result:
            total = row.total_searches or 0
            failed = row.failed_searches or 0
            
            success_rate = 0
            if total > 0:
                success_rate = round((total - failed) / total * 100, 1)
            
            sites_comparison.append({
                "site_id": row.id,
                "domain": row.domain,
                "total_searches": total,
                "unique_queries": row.unique_queries or 0,
                "avg_results": round(float(row.avg_results or 0), 1),
                "avg_time_ms": round(float(row.avg_time or 0), 1),
                "failed_searches": failed,
                "success_rate_percent": success_rate
            })
        
        return sites_comparison
    
    @staticmethod
    async def get_query_trends(
        db: AsyncSession,
        query: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get time series trend for a specific query.
        
        Args:
            db: Database session
            query: Search query to analyze
            days: Number of days to include
            
        Returns:
            List of daily trend data for the query
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        try:
            # PostgreSQL-style date truncation
            select_query = select(
                func.date_trunc('day', SearchQuery.timestamp).label("date"),
                func.count(SearchQuery.id).label("count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time")
            ).where(
                SearchQuery.query == query,
                SearchQuery.timestamp >= since
            ).group_by(func.date_trunc('day', SearchQuery.timestamp)).order_by("date")
            
            result = await db.execute(select_query)
        except Exception:
            # SQLite-style date truncation using strftime
            select_query = select(
                func.strftime('%Y-%m-%d', SearchQuery.timestamp).label("date"),
                func.count(SearchQuery.id).label("count"),
                func.avg(SearchQuery.results_count).label("avg_results"),
                func.avg(SearchQuery.response_time_ms).label("avg_time")
            ).where(
                SearchQuery.query == query,
                SearchQuery.timestamp >= since
            ).group_by(func.strftime('%Y-%m-%d', SearchQuery.timestamp)).order_by("date")
            
            result = await db.execute(select_query)
        
        trends = []
        for row in result:
            trends.append({
                "date": row.date,
                "count": row.count,
                "avg_results": round(float(row.avg_results or 0), 1),
                "avg_time_ms": round(float(row.avg_time or 0), 1)
            })
        
        return trends
    
    @staticmethod
    async def cleanup_old_queries(
        db: AsyncSession,
        days_to_keep: int = 90
    ) -> int:
        """
        Clean up old search queries to manage database size.
        
        Args:
            db: Database session
            days_to_keep: Number of days of data to keep
            
        Returns:
            Number of queries deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Count before deletion for logging
        count_query = select(func.count(SearchQuery.id)).where(
            SearchQuery.timestamp < cutoff_date
        )
        count = await db.scalar(count_query) or 0
        
        if count > 0:
            # Delete old queries
            delete_query = SearchQuery.__table__.delete().where(
                SearchQuery.timestamp < cutoff_date
            )
            await db.execute(delete_query)
            await db.commit()
        
        return count


# Helper function for case statement (SQLAlchemy doesn't have a built-in case for some dialects)
from sqlalchemy.sql import case