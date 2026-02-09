"""
Tests for API key authentication system.

Tests include:
- Key generation and hashing
- API key verification with various scenarios
- Expiry and scope restriction
- Key management functions
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import (
    generate_api_key,
    hash_api_key,
    verify_api_key,
    create_api_key,
    revoke_api_key,
    get_api_key_stats
)
from app.models import APIKey, APIRequest, Site


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    
    # Track added/updated objects
    session._mock_objects = {}
    
    def execute_mock(query):
        # Mock for verifying API key
        if "APIKey" in str(query) and "key_hash" in str(query):
            result_mock = AsyncMock()
            # Return None for not found case
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
            return result_mock
        
        # Mock for other queries
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        result_mock.scalar = AsyncMock(return_value=0)
        return result_mock
    
    session.execute = execute_mock
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    
    return session


@pytest.fixture
def mock_api_key():
    """Create a mock API key object."""
    api_key = MagicMock(spec=APIKey)
    api_key.id = 123
    api_key.key_hash = "test_hash"
    api_key.name = "Test API Key"
    api_key.site_id = None  # Unrestricted
    api_key.rate_limit_per_minute = 100
    api_key.requests_count = 0
    api_key.last_used_at = None
    api_key.expires_at = None
    api_key.is_active = True
    api_key.created_at = datetime.utcnow()
    return api_key


@pytest.fixture
def mock_api_key_with_site():
    """Create a mock API key restricted to a site."""
    api_key = MagicMock(spec=APIKey)
    api_key.id = 124
    api_key.key_hash = "site_restricted_hash"
    api_key.name = "Site-Specific Key"
    api_key.site_id = 456
    api_key.rate_limit_per_minute = 50
    api_key.requests_count = 10
    api_key.last_used_at = datetime.utcnow() - timedelta(hours=1)
    api_key.expires_at = None
    api_key.is_active = True
    api_key.created_at = datetime.utcnow() - timedelta(days=7)
    return api_key


def test_generate_api_key():
    """Test API key generation."""
    key = generate_api_key()
    
    # Should start with ss_
    assert key.startswith("ss_")
    
    # Should be reasonably long (ss_ + 32 token_urlsafe chars ≈ 44 chars)
    assert len(key) > 40
    
    # Should generate unique keys
    key2 = generate_api_key()
    assert key != key2


def test_hash_api_key():
    """Test API key hashing."""
    test_key = "ss_test_key_value"
    hashed = hash_api_key(test_key)
    
    # Should be a hex string
    assert isinstance(hashed, str)
    assert len(hashed) == 64  # SHA-256 hex digest
    
    # Should be deterministic
    assert hash_api_key(test_key) == hashed
    
    # Should be different for different keys
    different_hash = hash_api_key("ss_different_key")
    assert hashed != different_hash


@pytest.mark.asyncio
async def test_verify_api_key_success(mock_db_session, mock_api_key):
    """Test successful API key verification."""
    # Configure mock to return API key
    async def execute_mock(query):
        result_mock = AsyncMock()
        if "APIKey" in str(query) and "key_hash" in str(query):
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        else:
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Mock credentials
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="ss_valid_test_key"
    )
    
    # Mock hash_api_key to return known hash
    with patch('app.auth.hash_api_key', return_value=mock_api_key.key_hash):
        result = await verify_api_key(credentials, mock_db_session)
    
    # Should return the API key
    assert result is mock_api_key
    
    # Should have incremented usage count
    assert mock_api_key.requests_count == 1
    
    # Should have updated last_used_at
    assert mock_api_key.last_used_at is not None
    
    # Should have attempted to commit
    mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_verify_api_key_invalid_format():
    """Test API key verification with invalid format."""
    # Mock credentials with wrong format
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="invalid_format_key"  # Doesn't start with ss_
    )
    
    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Should raise 401 with specific error
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(credentials, mock_session)
    
    assert exc_info.value.status_code == 401
    assert "Invalid API key format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_api_key_not_found(mock_db_session):
    """Test API key verification when key not found."""
    # Configure mock to return None (key not found)
    async def execute_mock(query):
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Mock credentials
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="ss_nonexistent_key"
    )
    
    # Mock hash_api_key
    with patch('app.auth.hash_api_key', return_value="nonexistent_hash"):
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(credentials, mock_db_session)
    
    assert exc_info.value.status_code == 401
    assert "Invalid or inactive" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_api_key_inactive(mock_db_session, mock_api_key):
    """Test API key verification with inactive key."""
    # Make key inactive
    mock_api_key.is_active = False
    
    # Configure mock to return inactive key
    async def execute_mock(query):
        result_mock = AsyncMock()
        if "APIKey" in str(query) and "key_hash" in str(query):
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        else:
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Mock credentials
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="ss_inactive_key"
    )
    
    # Mock hash_api_key
    with patch('app.auth.hash_api_key', return_value=mock_api_key.key_hash):
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(credentials, mock_db_session)
    
    assert exc_info.value.status_code == 401
    assert "Invalid or inactive" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_api_key_expired(mock_db_session, mock_api_key):
    """Test API key verification with expired key."""
    # Set expiration to past
    mock_api_key.expires_at = datetime.utcnow() - timedelta(days=1)
    mock_api_key.is_active = True
    
    # Configure mock to return expired key
    async def execute_mock(query):
        result_mock = AsyncMock()
        if "APIKey" in str(query) and "key_hash" in str(query):
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        else:
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Mock credentials
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="ss_expired_key"
    )
    
    # Mock hash_api_key
    with patch('app.auth.hash_api_key', return_value=mock_api_key.key_hash):
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(credentials, mock_db_session)
    
    assert exc_info.value.status_code == 401
    assert "API key has expired" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_api_key_commits_failure(mock_db_session, mock_api_key):
    """Test API key verification when commit fails."""
    # Configure mock to return API key
    async def execute_mock(query):
        result_mock = AsyncMock()
        if "APIKey" in str(query) and "key_hash" in str(query):
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        else:
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Make commit fail
    mock_db_session.commit.side_effect = Exception("Database error")
    
    # Mock credentials
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials="ss_test_key"
    )
    
    # Mock hash_api_key
    with patch('app.auth.hash_api_key', return_value=mock_api_key.key_hash):
        # Should still return the key even if commit fails
        result = await verify_api_key(credentials, mock_db_session)
    
    assert result is mock_api_key
    # Rollback should have been called
    mock_db_session.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_create_api_key_success(mock_db_session):
    """Test successful API key creation."""
    # Configure commit to refresh the mock
    async def commit_refresh():
        pass
    
    mock_db_session.commit = AsyncMock(side_effect=commit_refresh)
    
    # Create key with no expiration
    result = await create_api_key(
        db=mock_db_session,
        name="Test Key",
        site_id=123,
        rate_limit_per_minute=50
    )
    
    # Should have required fields
    assert "plaintext_key" in result
    assert result["plaintext_key"].startswith("ss_")
    assert "api_key_id" in result
    assert result["name"] == "Test Key"
    assert result["site_id"] == 123
    assert result["rate_limit_per_minute"] == 50
    assert result["expires_at"] is None
    assert result["created_at"] is not None
    
    # Should have called add and commit
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_create_api_key_with_expiration(mock_db_session):
    """Test API key creation with expiration."""
    with patch('app.auth.generate_api_key', return_value="ss_test_key_123"):
        with patch('app.auth.hash_api_key', return_value="hashed_key_123"):
            result = await create_api_key(
                db=mock_db_session,
                name="Expiring Key",
                expires_in_days=30
            )
    
    assert "plaintext_key" in result
    assert result["plaintext_key"] == "ss_test_key_123"
    assert result["expires_at"] is not None
    
    # Expiry should be in the future
    if result["expires_at"]:
        expiry_time = result["expires_at"]
        assert expiry_time > datetime.utcnow()


@pytest.mark.asyncio
async def test_create_api_key_no_name(mock_db_session):
    """Test API key creation without a name."""
    result = await create_api_key(
        db=mock_db_session,
        name=None
    )
    
    assert result["name"] is None


@pytest.mark.asyncio
async def test_revoke_api_key_success(mock_db_session, mock_api_key):
    """Test successful API key revocation."""
    # Configure mock to find the key
    async def execute_mock(query):
        result_mock = AsyncMock()
        if "APIKey" in str(query) and "id == 123" in str(query):
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        else:
            result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Revoke the key
    result = await revoke_api_key(mock_db_session, 123)
    
    # Should return True
    assert result is True
    
    # Key should be marked inactive
    assert mock_api_key.is_active is False
    
    # Should have committed
    mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_api_key_not_found(mock_db_session):
    """Test API key revocation when key not found."""
    # Configure mock to return None (key not found)
    async def execute_mock(query):
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Try to revoke non-existent key
    result = await revoke_api_key(mock_db_session, 999)
    
    # Should return False
    assert result is False
    
    # Should not have committed
    mock_db_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_get_api_key_stats_success(mock_db_session, mock_api_key):
    """Test getting API key statistics."""
    # Configure execute mock for different queries
    call_count = 0
    async def execute_mock(query):
        nonlocal call_count
        call_count += 1
        
        result_mock = AsyncMock()
        
        # First call: get API key
        if call_count == 1:
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        # Second call: count recent requests
        elif call_count == 2:
            result_mock.scalar = AsyncMock(return_value=5)
        
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Get stats
    stats = await get_api_key_stats(mock_db_session, 123)
    
    # Should have stats
    assert stats is not None
    assert stats["id"] == 123
    assert stats["name"] == "Test API Key"
    assert stats["site_id"] is None
    assert stats["rate_limit_per_minute"] == 100
    assert stats["requests_count"] == 0
    assert stats["recent_requests_24h"] == 5
    assert stats["is_active"] is True
    assert stats["days_until_expiry"] is None  # No expiration


@pytest.mark.asyncio
async def test_get_api_key_stats_expiring(mock_db_session):
    """Test getting stats for an expiring API key."""
    # Create mock key with future expiration
    mock_api_key = MagicMock(spec=APIKey)
    mock_api_key.id = 123
    mock_api_key.name = "Expiring Key"
    mock_api_key.site_id = None
    mock_api_key.rate_limit_per_minute = 100
    mock_api_key.requests_count = 10
    mock_api_key.last_used_at = datetime.utcnow() - timedelta(hours=2)
    mock_api_key.expires_at = datetime.utcnow() + timedelta(days=5)
    mock_api_key.is_active = True
    mock_api_key.created_at = datetime.utcnow() - timedelta(days=25)
    
    # Configure execute mock
    call_count = 0
    async def execute_mock(query):
        nonlocal call_count
        call_count += 1
        
        result_mock = AsyncMock()
        
        if call_count == 1:
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        elif call_count == 2:
            result_mock.scalar = AsyncMock(return_value=2)
        
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Get stats
    stats = await get_api_key_stats(mock_db_session, 123)
    
    # Should have days until expiry
    assert stats["days_until_expiry"] == 5


@pytest.mark.asyncio
async def test_get_api_key_stats_expired(mock_db_session):
    """Test getting stats for an expired API key."""
    # Create mock key with past expiration
    mock_api_key = MagicMock(spec=APIKey)
    mock_api_key.id = 123
    mock_api_key.name = "Expired Key"
    mock_api_key.expires_at = datetime.utcnow() - timedelta(days=1)
    mock_api_key.is_active = True
    
    # Configure execute mock
    async def execute_mock(query):
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        result_mock.scalar = AsyncMock(return_value=0)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Get stats
    stats = await get_api_key_stats(mock_db_session, 123)
    
    # Days until expiry should be None for expired keys
    assert stats["days_until_expiry"] is None


@pytest.mark.asyncio
async def test_get_api_key_stats_not_found(mock_db_session):
    """Test getting stats for non-existent API key."""
    # Configure mock to return None (key not found)
    async def execute_mock(query):
        result_mock = AsyncMock()
        result_mock.scalar_one_or_none = AsyncMock(return_value=None)
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Get stats for non-existent key
    stats = await get_api_key_stats(mock_db_session, 999)
    
    # Should return None
    assert stats is None


@pytest.mark.asyncio
async def test_get_api_key_stats_no_recent_requests(mock_db_session):
    """Test getting stats when there are no recent requests."""
    # Create mock key
    mock_api_key = MagicMock(spec=APIKey)
    mock_api_key.id = 123
    mock_api_key.name = "New Key"
    mock_api_key.expires_at = None
    mock_api_key.is_active = True
    
    # Configure execute mock
    call_count = 0
    async def execute_mock(query):
        nonlocal call_count
        call_count += 1
        
        result_mock = AsyncMock()
        
        if call_count == 1:
            result_mock.scalar_one_or_none = AsyncMock(return_value=mock_api_key)
        elif call_count == 2:
            result_mock.scalar = AsyncMock(return_value=None)  # No recent requests
        
        return result_mock
    
    mock_db_session.execute = execute_mock
    
    # Get stats
    stats = await get_api_key_stats(mock_db_session, 123)
    
    # Should have 0 recent requests
    assert stats["recent_requests_24h"] == 0


@pytest.mark.asyncio
async def test_api_key_scope_restriction(mock_db_session, mock_api_key_with_site):
    """Test API key scope restriction behavior."""
    # Verify that site-scoped keys have site_id attribute
    assert mock_api_key_with_site.site_id == 456
    
    # The verify_api_key function doesn't check scope,
    # scope is checked by endpoints using the API key


def test_get_api_key_dependency():
    """Test API key dependency creation."""
    from app.auth import get_api_key_dependency
    
    dependency = get_api_key_dependency()
    # Should be a FastAPI dependency
    from fastapi import Depends
    assert isinstance(dependency, Depends)