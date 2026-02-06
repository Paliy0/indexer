"""
Database connection and session management for async SQLAlchemy.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from app.config import get_settings
from app.models import Base

settings = get_settings()

# Create async engine
# Convert postgresql:// to postgresql+asyncpg:// for async support
# For SQLite, use aiosqlite for async support
database_url = settings.database_url

if database_url.startswith("postgresql://"):
    # Use asyncpg for PostgreSQL
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif database_url.startswith("sqlite"):
    # Use aiosqlite for SQLite async support
    database_url = database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

# Create async engine with appropriate settings
engine = create_async_engine(
    database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=20 if "postgresql" in database_url else 5,
    max_overflow=0,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database sessions.
    
    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables.
    Creates all tables defined in models.
    
    Note: In production, use Alembic migrations instead.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db():
    """
    Drop all database tables.
    WARNING: This will delete all data!
    Only use in development/testing.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
