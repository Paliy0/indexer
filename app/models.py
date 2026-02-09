"""
SQLAlchemy ORM models for PostgreSQL database.
"""

from typing import Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, CheckConstraint, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import json

# Import SiteConfig from site_config module
from app.site_config import SiteConfig, DEFAULT_CONFIG

Base = declarative_base()


def get_default_config() -> Dict[str, Any]:
    """Get default configuration as a dictionary."""
    return DEFAULT_CONFIG.dict()


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
    config = Column(JSON, default=get_default_config, nullable=False)
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
    api_keys = relationship("APIKey", back_populates="site", cascade="all, delete-orphan")
    
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


class APIKey(Base):
    """
    API Key model for authentication and rate limiting.
    
    Stores hashed keys only (never plaintext).
    """
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hex digest
    name = Column(String(255), nullable=True)  # User-provided name for the key
    
    # Scope restrictions (optional)
    # Note: users table doesn't exist yet, so user_id is commented out
    # user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), nullable=True)
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=100, nullable=False)
    
    # Usage tracking
    requests_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Lifecycle
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    site = relationship("Site", back_populates="api_keys")
    api_requests = relationship("APIRequest", back_populates="api_key", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<APIKey(id={self.id}, name='{self.name}', active={self.is_active})>"


class APIRequest(Base):
    """
    Logs all API requests for analytics and auditing.
    """
    __tablename__ = "api_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    api_key = relationship("APIKey", back_populates="api_requests")


class SearchQuery(Base):
    """
    Model for logging search queries for analytics.
    
    Attributes:
        id: Primary key (big integer for high volume)
        site_id: Foreign key to sites table (optional, for site-specific analytics)
        query: Search query string (max 500 chars)
        results_count: Number of results found
        response_time_ms: Time taken to process the search in milliseconds
        ip_address: IP address of the requester (for geo-analytics)
        timestamp: When the search was performed
    """
    __tablename__ = "search_queries"
    
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(
        Integer,
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    query = Column(String(500), nullable=False, index=True)
    results_count = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)  # Store IP as string for compatibility
    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    # Relationships
    site = relationship("Site", backref="search_queries")
    
    def __repr__(self):
        return f"<SearchQuery(id={self.id}, query='{self.query}', results={self.results_count})>"