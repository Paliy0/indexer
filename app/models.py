"""
SQLAlchemy ORM models for PostgreSQL database.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Site(Base):
    """
    Site model representing a website being indexed.
    
    Attributes:
        id: Primary key
        url: Original URL of the site
        domain: Domain name (unique identifier)
        status: Current scraping status (pending, scraping, completed, failed)
        page_count: Number of pages indexed
        config: JSONB/JSON configuration for scraping
        last_scraped: Timestamp of last successful scrape
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "sites"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        server_default="pending"
    )
    page_count = Column(Integer, default=0, nullable=False, server_default="0")
    # Use JSON for SQLite compatibility, will be JSONB in PostgreSQL
    config = Column(JSON, default=dict, nullable=False)
    last_scraped = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    pages = relationship("Page", back_populates="site", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'scraping', 'completed', 'failed')",
            name="check_site_status"
        ),
    )
    
    def __repr__(self):
        return f"<Site(id={self.id}, domain='{self.domain}', status='{self.status}')>"


class Page(Base):
    """
    Page model representing a single indexed page from a site.
    
    Attributes:
        id: Primary key
        site_id: Foreign key to sites table
        url: Full URL of the page
        title: Page title
        content: Extracted text content
        page_metadata: JSONB/JSON metadata (headers, links, word count, etc.)
        indexed_at: When the page was indexed
        created_at: Creation timestamp
    """
    __tablename__ = "pages"
    
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer,
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    url = Column(String(2048), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    # Use JSON for SQLite compatibility, will be JSONB in PostgreSQL
    page_metadata = Column(JSON, default=dict, nullable=False)
    indexed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationships
    site = relationship("Site", back_populates="pages")
    
    def __repr__(self):
        return f"<Page(id={self.id}, url='{self.url}', site_id={self.site_id})>"
