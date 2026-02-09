"""
Unit tests for analytics module - search query logging and statistics
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.models import Base, Site, SearchQuery
from app.analytics import Analytics


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


@pytest_asyncio.fixture
async def test_site(async_session):
    """Create a test site for analytics"""
    site = Site(
        domain="test-site.com",
        url="https://test-site.com",
        status="completed",
        page_count=10,
    )
    async_session.add(site)
    await async_session.commit()
    await async_session.refresh(site)
    return site


@pytest.mark.asyncio
async def test_log_search_query_basic(async_session):
    """Test logging a basic search query"""
    # Log a search query
    search_query = await Analytics.log_search_query(
        db=async_session,
        query="test query",
        results_count=5,
        response_time_ms=150,
    )
    
    # Verify the query was logged
    assert search_query.id is not None
    assert search_query.query == "test query"
    assert search_query.results_count == 5
    assert search_query.response_time_ms == 150
    assert search_query.site_id is None
    assert search_query.timestamp is not None


@pytest.mark.asyncio
async def test_log_search_query_with_site(async_session, test_site):
    """Test logging a search query with site association"""
    # Log a search query for a specific site
    search_query = await Analytics.log_search_query(
        db=async_session,
        query="site-specific query",
        results_count=12,
        response_time_ms=200,
        site_id=test_site.id,
    )
    
    # Verify the query was logged with site association
    assert search_query.query == "site-specific query"
    assert search_query.site_id == test_site.id
    assert search_query.results_count == 12


@pytest.mark.asyncio
async def test_log_search_query_with_ip(async_session):
    """Test logging a search query with IP address"""
    # Log a search query with IP address
    search_query = await Analytics.log_search_query(
        db=async_session,
        query="query from ip",
        ip_address="192.168.1.100",
    )
    
    # Verify the IP was logged
    assert search_query.query == "query from ip"
    assert search_query.ip_address == "192.168.1.100"


@pytest.mark.asyncio
async def test_log_search_query_minimal(async_session):
    """Test logging a search query with minimal information"""
    # Log a search query with only query string
    search_query = await Analytics.log_search_query(
        db=async_session,
        query="minimal query",
    )
    
    # Verify the query was logged
    assert search_query.query == "minimal query"
    assert search_query.results_count is None
    assert search_query.response_time_ms is None
    assert search_query.site_id is None
    assert search_query.ip_address is None


@pytest.mark.asyncio
async def test_get_search_stats_empty(async_session):
    """Test getting search stats when no queries exist"""
    # Get stats for empty database
    stats = await Analytics.get_search_stats(async_session, days=30)
    
    # Verify empty stats
    assert stats["total_searches"] == 0
    assert stats["unique_queries"] == 0
    assert stats["failed_searches"] == 0
    assert stats["avg_results_per_query"] == 0.0
    assert stats["avg_response_time_ms"] == 0.0
    assert stats["success_rate_percent"] == 0
    assert stats["recent_searches_24h"] == 0
    assert stats["top_queries"] == []
    assert stats["searches_by_day"] == []


@pytest.mark.asyncio
async def test_get_search_stats_with_queries(async_session):
    """Test getting search stats with multiple queries"""
    # Log multiple search queries
    queries = [
        ("test query 1", 10, 100),
        ("test query 1", 8, 120),  # Duplicate query
        ("test query 2", 0, 50),   # Failed search
        ("test query 3", 15, 200),
        ("test query 4", 5, 80),
    ]
    
    for query, results, time_ms in queries:
        await Analytics.log_search_query(
            db=async_session,
            query=query,
            results_count=results,
            response_time_ms=time_ms,
        )
    
    # Get stats
    stats = await Analytics.get_search_stats(async_session, days=30)
    
    # Verify stats
    assert stats["total_searches"] == 5
    assert stats["unique_queries"] == 4  # test query 1 appears twice
    assert stats["failed_searches"] == 1  # query with 0 results
    assert stats["avg_results_per_query"] == (10 + 8 + 15 + 5) / 4  # Exclude failed
    assert stats["avg_response_time_ms"] == (100 + 120 + 50 + 200 + 80) / 5
    assert stats["success_rate_percent"] == 80.0  # 4 out of 5 succeeded
    
    # Check top queries
    assert len(stats["top_queries"]) == 4  # Should have all unique queries
    top_query = stats["top_queries"][0]
    assert top_query["query"] == "test query 1"
    assert top_query["count"] == 2
    assert top_query["avg_results"] == 9.0  # (10 + 8) / 2
    assert top_query["avg_time_ms"] == 110.0  # (100 + 120) / 2


@pytest.mark.asyncio
async def test_get_search_stats_with_site_filter(async_session, test_site):
    """Test getting search stats filtered by site"""
    # Create another site
    other_site = Site(
        domain="other-site.com",
        url="https://other-site.com",
        status="completed",
        page_count=5,
    )
    async_session.add(other_site)
    await async_session.commit()
    
    # Log queries for both sites
    queries = [
        ("query 1", 10, 100, test_site.id),
        ("query 2", 5, 80, test_site.id),
        ("query 3", 8, 120, other_site.id),
    ]
    
    for query, results, time_ms, site_id in queries:
        await Analytics.log_search_query(
            db=async_session,
            query=query,
            results_count=results,
            response_time_ms=time_ms,
            site_id=site_id,
        )
    
    # Get stats for test_site only
    stats = await Analytics.get_search_stats(async_session, site_id=test_site.id, days=30)
    
    # Verify only queries for test_site are counted
    assert stats["total_searches"] == 2
    assert stats["unique_queries"] == 2
    assert stats["avg_results_per_query"] == (10 + 5) / 2
    assert stats["avg_response_time_ms"] == (100 + 80) / 2


@pytest.mark.asyncio
async def test_get_search_stats_time_filter(async_session):
    """Test getting search stats with time filtering"""
    # Log queries with different timestamps (simulating old queries)
    current_time = datetime.now(timezone.utc)
    
    # Log a query that's 45 days old (outside 30-day window)
    old_query = SearchQuery(
        query="old query",
        results_count=5,
        response_time_ms=100,
        timestamp=current_time - timedelta(days=45),
    )
    async_session.add(old_query)
    await async_session.commit()
    
    # Log recent queries
    recent_queries = [
        ("recent query 1", 10, 150),
        ("recent query 2", 8, 120),
    ]
    
    for query, results, time_ms in recent_queries:
        await Analytics.log_search_query(
            db=async_session,
            query=query,
            results_count=results,
            response_time_ms=time_ms,
        )
    
    # Get stats for last 30 days
    stats = await Analytics.get_search_stats(async_session, days=30)
    
    # Should only include recent queries
    assert stats["total_searches"] == 2  # Not 3
    assert stats["unique_queries"] == 2


@pytest.mark.asyncio
async def test_get_search_stats_different_periods(async_session):
    """Test getting search stats with different time periods"""
    # Log queries
    queries = [
        ("query 1", 10, 100),
        ("query 2", 5, 80),
        ("query 3", 8, 120),
    ]
    
    for query, results, time_ms in queries:
        await Analytics.log_search_query(
            db=async_session,
            query=query,
            results_count=results,
            response_time_ms=time_ms,
        )
    
    # Test with different periods
    stats_7 = await Analytics.get_search_stats(async_session, days=7)
    stats_30 = await Analytics.get_search_stats(async_session, days=30)
    stats_90 = await Analytics.get_search_stats(async_session, days=90)
    
    # All should have the same queries since all are recent
    assert stats_7["total_searches"] == 3
    assert stats_30["total_searches"] == 3
    assert stats_90["total_searches"] == 3
    
    # Period should be reflected in the stats
    assert stats_7["period_days"] == 7
    assert stats_30["period_days"] == 30
    assert stats_90["period_days"] == 90


@pytest.mark.asyncio
async def test_get_searches_by_day(async_session):
    """Test getting searches grouped by day"""
    # Log multiple queries (all same day in this test)
    queries = [
        ("query 1", 10, 100),
        ("query 2", 5, 80),
        ("query 3", 8, 120),
    ]
    
    for query, results, time_ms in queries:
        await Analytics.log_search_query(
            db=async_session,
            query=query,
            results_count=results,
            response_time_ms=time_ms,
        )
    
    # Get searches by day
    stats = await Analytics.get_search_stats(async_session, days=30)
    searches_by_day = stats["searches_by_day"]
    
    # Should have at least one day of data
    assert len(searches_by_day) > 0
    
    # Check structure of daily data
    day_data = searches_by_day[0]
    assert "date" in day_data
    assert "count" in day_data
    assert "avg_results" in day_data
    assert "avg_time_ms" in day_data
    assert day_data["count"] == 3  # All queries on same day


@pytest.mark.asyncio
async def test_get_site_comparison(async_session):
    """Test comparing search activity across sites"""
    # Create multiple sites
    sites = []
    for i in range(3):
        site = Site(
            domain=f"site{i}.com",
            url=f"https://site{i}.com",
            status="completed",
            page_count=i * 10,
        )
        async_session.add(site)
        sites.append(site)
    await async_session.commit()
    
    # Log queries for each site
    # Site 0: 2 queries (1 failed)
    await Analytics.log_search_query(
        db=async_session,
        query="site0 query 1",
        results_count=5,
        response_time_ms=100,
        site_id=sites[0].id,
    )
    await Analytics.log_search_query(
        db=async_session,
        query="site0 query 2",
        results_count=0,  # Failed
        response_time_ms=50,
        site_id=sites[0].id,
    )
    
    # Site 1: 1 query
    await Analytics.log_search_query(
        db=async_session,
        query="site1 query",
        results_count=10,
        response_time_ms=150,
        site_id=sites[1].id,
    )
    
    # Site 2: 0 queries
    
    # Get site comparison
    comparison = await Analytics.get_site_comparison(async_session, days=30)
    
    # Should have data for sites with queries
    assert len(comparison) == 2  # Site 0 and 1, not Site 2
    
    # Check site 0 data
    site0_data = next(s for s in comparison if s["domain"] == "site0.com")
    assert site0_data["total_searches"] == 2
    assert site0_data["failed_searches"] == 1
    assert site0_data["success_rate_percent"] == 50.0
    
    # Check site 1 data
    site1_data = next(s for s in comparison if s["domain"] == "site1.com")
    assert site1_data["total_searches"] == 1
    assert site1_data["failed_searches"] == 0
    assert site1_data["success_rate_percent"] == 100.0


@pytest.mark.asyncio
async def test_get_query_trends(async_session):
    """Test getting time series trends for a specific query"""
    # Log multiple instances of the same query
    for i in range(5):
        await Analytics.log_search_query(
            db=async_session,
            query="popular query",
            results_count=i * 3,
            response_time_ms=100 + i * 10,
        )
    
    # Get query trends
    trends = await Analytics.get_query_trends(async_session, query="popular query", days=30)
    
    # Should have trend data
    assert len(trends) > 0
    
    # Check structure
    trend_data = trends[0]
    assert "date" in trend_data
    assert "count" in trend_data
    assert "avg_results" in trend_data
    assert "avg_time_ms" in trend_data


@pytest.mark.asyncio
async def test_cleanup_old_queries(async_session):
    """Test cleaning up old search queries"""
    current_time = datetime.now(timezone.utc)
    
    # Create old queries (91 days old)
    old_queries = []
    for i in range(3):
        query = SearchQuery(
            query=f"old query {i}",
            results_count=5,
            response_time_ms=100,
            timestamp=current_time - timedelta(days=91),
        )
        async_session.add(query)
        old_queries.append(query)
    
    # Create recent queries
    recent_queries = []
    for i in range(2):
        query = await Analytics.log_search_query(
            db=async_session,
            query=f"recent query {i}",
            results_count=10,
            response_time_ms=150,
        )
        recent_queries.append(query)
    
    # Clean up queries older than 90 days
    deleted_count = await Analytics.cleanup_old_queries(async_session, days_to_keep=90)
    
    # Should delete 3 old queries
    assert deleted_count == 3
    
    # Verify old queries are deleted
    result = await async_session.execute(
        select(SearchQuery).where(SearchQuery.query.like("old query%"))
    )
    remaining_old = result.scalars().all()
    assert len(remaining_old) == 0
    
    # Verify recent queries remain
    result = await async_session.execute(
        select(SearchQuery).where(SearchQuery.query.like("recent query%"))
    )
    remaining_recent = result.scalars().all()
    assert len(remaining_recent) == 2


@pytest.mark.asyncio
async def test_cleanup_no_old_queries(async_session):
    """Test cleanup when no old queries exist"""
    # Create only recent queries
    await Analytics.log_search_query(
        db=async_session,
        query="recent query",
        results_count=10,
        response_time_ms=150,
    )
    
    # Clean up queries older than 90 days
    deleted_count = await Analytics.cleanup_old_queries(async_session, days_to_keep=90)
    
    # Should delete 0 queries
    assert deleted_count == 0
    
    # Verify query still exists
    result = await async_session.execute(
        select(SearchQuery).where(SearchQuery.query == "recent query")
    )
    remaining = result.scalar_one_or_none()
    assert remaining is not None