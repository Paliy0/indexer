"""
Unit tests for SQLAlchemy ORM models - async CRUD operations
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from app.models import Base, Site, Page


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


class TestSiteModel:
    """Test Site model CRUD operations"""
    
    @pytest.mark.asyncio
    async def test_create_site(self, async_session):
        """Test creating a new site"""
        site = Site(
            url="https://example.com",
            domain="example.com",
            status="pending",
            page_count=0
        )
        
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        assert site.id is not None
        assert site.url == "https://example.com"
        assert site.domain == "example.com"
        assert site.status == "pending"
        assert site.page_count == 0
        assert site.created_at is not None
        assert site.updated_at is not None
    
    @pytest.mark.asyncio
    async def test_site_default_values(self, async_session):
        """Test Site model default values"""
        site = Site(
            url="https://test.com",
            domain="test.com"
        )
        
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        assert site.status == "pending"
        assert site.page_count == 0
        assert site.config == {}
        assert site.last_scraped is None
    
    @pytest.mark.asyncio
    async def test_site_unique_domain_constraint(self, async_session):
        """Test that duplicate domain raises IntegrityError"""
        site1 = Site(
            url="https://example.com",
            domain="example.com"
        )
        async_session.add(site1)
        await async_session.commit()
        
        # Try to create another site with same domain
        site2 = Site(
            url="https://example.com/other",
            domain="example.com"
        )
        async_session.add(site2)
        
        with pytest.raises(IntegrityError):
            await async_session.commit()
    
    @pytest.mark.asyncio
    async def test_site_status_values(self, async_session):
        """Test valid status values for Site"""
        valid_statuses = ["pending", "scraping", "completed", "failed"]
        
        for idx, status in enumerate(valid_statuses):
            site = Site(
                url=f"https://example{idx}.com",
                domain=f"example{idx}.com",
                status=status
            )
            async_session.add(site)
        
        await async_session.commit()
        
        # Verify all sites were created
        result = await async_session.execute(select(Site))
        sites = result.scalars().all()
        assert len(sites) == 4
        
        statuses = {s.status for s in sites}
        assert statuses == set(valid_statuses)
    
    @pytest.mark.asyncio
    async def test_update_site(self, async_session):
        """Test updating site fields"""
        site = Site(
            url="https://example.com",
            domain="example.com",
            status="pending"
        )
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        site_id = site.id
        
        # Update site
        site.status = "completed"
        site.page_count = 42
        site.last_scraped = datetime.now(timezone.utc)
        await async_session.commit()
        
        # Reload and verify
        result = await async_session.execute(
            select(Site).where(Site.id == site_id)
        )
        updated_site = result.scalar_one()
        
        assert updated_site.status == "completed"
        assert updated_site.page_count == 42
        assert updated_site.last_scraped is not None
    
    @pytest.mark.asyncio
    async def test_delete_site(self, async_session):
        """Test deleting a site"""
        site = Site(
            url="https://example.com",
            domain="example.com"
        )
        async_session.add(site)
        await async_session.commit()
        
        site_id = site.id
        
        # Delete site
        await async_session.delete(site)
        await async_session.commit()
        
        # Verify deletion
        result = await async_session.execute(
            select(Site).where(Site.id == site_id)
        )
        deleted_site = result.scalar_one_or_none()
        assert deleted_site is None
    
    @pytest.mark.asyncio
    async def test_query_sites(self, async_session):
        """Test querying sites"""
        # Create multiple sites
        sites_data = [
            ("https://example.com", "example.com", "completed"),
            ("https://test.com", "test.com", "pending"),
            ("https://demo.com", "demo.com", "scraping"),
        ]
        
        for url, domain, status in sites_data:
            site = Site(url=url, domain=domain, status=status)
            async_session.add(site)
        
        await async_session.commit()
        
        # Query all sites
        result = await async_session.execute(select(Site))
        all_sites = result.scalars().all()
        assert len(all_sites) == 3
        
        # Query by status
        result = await async_session.execute(
            select(Site).where(Site.status == "completed")
        )
        completed_sites = result.scalars().all()
        assert len(completed_sites) == 1
        assert completed_sites[0].domain == "example.com"
        
        # Query by domain
        result = await async_session.execute(
            select(Site).where(Site.domain == "test.com")
        )
        test_site = result.scalar_one_or_none()
        assert test_site is not None
        assert test_site.status == "pending"


class TestPageModel:
    """Test Page model CRUD operations"""
    
    @pytest.mark.asyncio
    async def test_create_page(self, async_session):
        """Test creating a new page"""
        # Create a site first
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        # Create a page
        page = Page(
            site_id=site.id,
            url="https://example.com/page1",
            title="Test Page",
            content="This is test content for the page.",
            page_metadata={"word_count": 7}
        )
        
        async_session.add(page)
        await async_session.commit()
        await async_session.refresh(page)
        
        assert page.id is not None
        assert page.site_id == site.id
        assert page.url == "https://example.com/page1"
        assert page.title == "Test Page"
        assert page.content == "This is test content for the page."
        assert page.page_metadata == {"word_count": 7}
        assert page.indexed_at is not None
        assert page.created_at is not None
    
    @pytest.mark.asyncio
    async def test_page_default_metadata(self, async_session):
        """Test Page model default metadata value"""
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        page = Page(
            site_id=site.id,
            url="https://example.com/page1",
            title="Test",
            content="Content"
        )
        
        async_session.add(page)
        await async_session.commit()
        await async_session.refresh(page)
        
        assert page.page_metadata == {}
    
    @pytest.mark.asyncio
    async def test_page_site_relationship(self, async_session):
        """Test the relationship between Page and Site"""
        # Create site
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        # Create pages
        page1 = Page(
            site_id=site.id,
            url="https://example.com/page1",
            title="Page 1",
            content="Content 1"
        )
        page2 = Page(
            site_id=site.id,
            url="https://example.com/page2",
            title="Page 2",
            content="Content 2"
        )
        
        async_session.add(page1)
        async_session.add(page2)
        await async_session.commit()
        
        # Query site with pages
        result = await async_session.execute(
            select(Site).where(Site.id == site.id)
        )
        site_with_pages = result.scalar_one()
        
        # Access relationship
        await async_session.refresh(site_with_pages, ['pages'])
        assert len(site_with_pages.pages) == 2
        
        page_titles = {p.title for p in site_with_pages.pages}
        assert page_titles == {"Page 1", "Page 2"}
    
    @pytest.mark.asyncio
    async def test_cascade_delete(self, async_session):
        """Test that deleting a site cascades to pages"""
        # Create site with pages
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        page1 = Page(site_id=site.id, url="https://example.com/p1", title="P1", content="C1")
        page2 = Page(site_id=site.id, url="https://example.com/p2", title="P2", content="C2")
        async_session.add(page1)
        async_session.add(page2)
        await async_session.commit()
        
        # Delete site
        await async_session.delete(site)
        await async_session.commit()
        
        # Verify pages are also deleted
        result = await async_session.execute(select(Page))
        remaining_pages = result.scalars().all()
        assert len(remaining_pages) == 0
    
    @pytest.mark.asyncio
    async def test_query_pages_by_site(self, async_session):
        """Test querying pages filtered by site_id"""
        # Create two sites
        site1 = Site(url="https://example.com", domain="example.com")
        site2 = Site(url="https://test.com", domain="test.com")
        async_session.add(site1)
        async_session.add(site2)
        await async_session.commit()
        await async_session.refresh(site1)
        await async_session.refresh(site2)
        
        # Create pages for both sites
        page1 = Page(site_id=site1.id, url="https://example.com/p1", title="E1", content="C1")
        page2 = Page(site_id=site1.id, url="https://example.com/p2", title="E2", content="C2")
        page3 = Page(site_id=site2.id, url="https://test.com/p1", title="T1", content="C3")
        
        async_session.add_all([page1, page2, page3])
        await async_session.commit()
        
        # Query pages for site1
        result = await async_session.execute(
            select(Page).where(Page.site_id == site1.id)
        )
        site1_pages = result.scalars().all()
        assert len(site1_pages) == 2
        assert all(p.site_id == site1.id for p in site1_pages)
        
        # Query pages for site2
        result = await async_session.execute(
            select(Page).where(Page.site_id == site2.id)
        )
        site2_pages = result.scalars().all()
        assert len(site2_pages) == 1
        assert site2_pages[0].title == "T1"
    
    @pytest.mark.asyncio
    async def test_update_page(self, async_session):
        """Test updating page content"""
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        page = Page(
            site_id=site.id,
            url="https://example.com/page1",
            title="Original Title",
            content="Original content"
        )
        async_session.add(page)
        await async_session.commit()
        
        page_id = page.id
        
        # Update page
        page.title = "Updated Title"
        page.content = "Updated content"
        page.page_metadata = {"updated": True}
        await async_session.commit()
        
        # Reload and verify
        result = await async_session.execute(
            select(Page).where(Page.id == page_id)
        )
        updated_page = result.scalar_one()
        
        assert updated_page.title == "Updated Title"
        assert updated_page.content == "Updated content"
        assert updated_page.page_metadata == {"updated": True}
    
    @pytest.mark.asyncio
    async def test_delete_page(self, async_session):
        """Test deleting a single page"""
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        page = Page(site_id=site.id, url="https://example.com/page1", title="Test", content="Content")
        async_session.add(page)
        await async_session.commit()
        
        page_id = page.id
        
        # Delete page
        await async_session.delete(page)
        await async_session.commit()
        
        # Verify deletion
        result = await async_session.execute(
            select(Page).where(Page.id == page_id)
        )
        deleted_page = result.scalar_one_or_none()
        assert deleted_page is None
        
        # Site should still exist
        result = await async_session.execute(
            select(Site).where(Site.id == site.id)
        )
        site_still_exists = result.scalar_one_or_none()
        assert site_still_exists is not None


class TestModelRepr:
    """Test model __repr__ methods"""
    
    @pytest.mark.asyncio
    async def test_site_repr(self, async_session):
        """Test Site __repr__ output"""
        site = Site(url="https://example.com", domain="example.com", status="pending")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        repr_str = repr(site)
        assert "Site" in repr_str
        assert str(site.id) in repr_str
        assert "example.com" in repr_str
        assert "pending" in repr_str
    
    @pytest.mark.asyncio
    async def test_page_repr(self, async_session):
        """Test Page __repr__ output"""
        site = Site(url="https://example.com", domain="example.com")
        async_session.add(site)
        await async_session.commit()
        await async_session.refresh(site)
        
        page = Page(
            site_id=site.id,
            url="https://example.com/page1",
            title="Test Page",
            content="Content"
        )
        async_session.add(page)
        await async_session.commit()
        await async_session.refresh(page)
        
        repr_str = repr(page)
        assert "Page" in repr_str
        assert str(page.id) in repr_str
        assert "https://example.com/page1" in repr_str
        assert str(site.id) in repr_str
