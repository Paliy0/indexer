"""
API key authentication system for the Site Search Platform.

Provides:
- APIKey SQLAlchemy model with SHA-256 hashed keys
- generate_api_key() function to create new keys
- verify_api_key() FastAPI dependency for authentication
- Key management utilities

Key format: ss_{token_urlsafe(32)}
"""

import secrets
import hashlib
from datetime import datetime, timedelta, UTC, UTC
from typing import Optional

from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func

from app.db import get_db
from app.models import APIKey, APIRequest

# Security scheme for API key authentication
security = HTTPBearer()


def generate_api_key() -> str:
    """
    Generate a new API key.
    
    Returns:
        Plaintext API key in format: ss_{token_urlsafe(32)}
    """
    token = secrets.token_urlsafe(32)
    return f"ss_{token}"


def hash_api_key(key: str) -> str:
    """
    Hash API key for secure storage.
    
    Args:
        key: Plaintext API key
        
    Returns:
        SHA-256 hex digest of the key
    """
    return hashlib.sha256(key.encode()).hexdigest()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """
    Verify API key from Authorization header.
    
    Format: Authorization: Bearer ss_xxxxx
    
    Args:
        credentials: HTTP Authorization credentials containing the API key
        db: Database session
        
    Returns:
        APIKey instance if valid
        
    Raises:
        HTTPException: 401 if invalid or expired
    """
    token = credentials.credentials
    
    # Validate key format
    if not token.startswith("ss_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Keys must start with 'ss_'"
        )
    
    # Hash and look up in database
    key_hash = hash_api_key(token)
    
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key"
        )
    
    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=401,
            detail="API key has expired"
        )
    
    # Update usage stats
    api_key.requests_count += 1
    api_key.last_used_at = datetime.now(UTC)
    
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Still return the key even if update fails
        pass
    
    return api_key


async def create_api_key(
    db: AsyncSession,
    name: Optional[str] = None,
    site_id: Optional[int] = None,
    rate_limit_per_minute: int = 100,
    expires_in_days: Optional[int] = None
) -> dict:
    """
    Create a new API key.
    
    Args:
        db: Database session
        name: Optional name for the key
        site_id: Optional site ID to restrict access to
        rate_limit_per_minute: Requests per minute limit
        expires_in_days: Optional expiration in days
        
    Returns:
        Dictionary with plaintext_key and api_key_id
    """
    # Generate plaintext key
    plaintext_key = generate_api_key()
    key_hash = hash_api_key(plaintext_key)
    
    # Calculate expiration if specified
    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)
    
    # Create API key record
    api_key = APIKey(
        key_hash=key_hash,
        name=name,
        site_id=site_id,
        rate_limit_per_minute=rate_limit_per_minute,
        expires_at=expires_at,
        is_active=True
    )
    
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    
    return {
        "plaintext_key": plaintext_key,
        "api_key_id": api_key.id,
        "name": api_key.name,
        "site_id": api_key.site_id,
        "rate_limit_per_minute": api_key.rate_limit_per_minute,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at
    }


async def revoke_api_key(
    db: AsyncSession,
    api_key_id: int
) -> bool:
    """
    Revoke an API key by setting is_active=False.
    
    Args:
        db: Database session
        api_key_id: ID of the API key to revoke
        
    Returns:
        True if revoked, False if not found
    """
    result = await db.execute(
        select(APIKey).where(APIKey.id == api_key_id)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        return False
    
    api_key.is_active = False
    await db.commit()
    
    return True


async def get_api_key_stats(
    db: AsyncSession,
    api_key_id: int
) -> Optional[dict]:
    """
    Get statistics for an API key.
    
    Args:
        db: Database session
        api_key_id: ID of the API key
        
    Returns:
        Dictionary with usage statistics or None if not found
    """
    result = await db.execute(
        select(APIKey).where(APIKey.id == api_key_id)
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        return None
    
    # Count recent requests (last 24 hours)
    result = await db.execute(
        select(func.count(APIRequest.id)).where(
            APIRequest.api_key_id == api_key_id,
            APIRequest.timestamp >= datetime.now(UTC) - timedelta(days=1)
        )
    )
    recent_requests = result.scalar() or 0
    
    return {
        "id": api_key.id,
        "name": api_key.name,
        "site_id": api_key.site_id,
        "rate_limit_per_minute": api_key.rate_limit_per_minute,
        "requests_count": api_key.requests_count,
        "recent_requests_24h": recent_requests,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "expires_at": api_key.expires_at,
        "is_active": api_key.is_active,
        "days_until_expiry": (
            (api_key.expires_at - datetime.now(UTC)).days
            if api_key.expires_at and api_key.expires_at > datetime.now(UTC)
            else None
        )
    }


# Dependency for endpoints that require API key
def get_api_key_dependency():
    """Create API key dependency for FastAPI endpoints."""
    return Depends(verify_api_key)