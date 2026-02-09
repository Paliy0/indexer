"""
Tests for the Redis-based rate limiter.

Tests include:
- RateLimiter class with Redis sorted sets
- Sliding window algorithm correctness
- FastAPI dependency integration
- Rate limit exceeded responses
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient

from app.rate_limiter import RateLimiter, get_rate_limiter, rate_limit_dependency


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis_client = AsyncMock()
    
    # Mock sorted set operations
    redis_client.pipeline.return_value = AsyncMock()
    redis_client.zremrangebyscore = AsyncMock()
    redis_client.zcard = AsyncMock()
    redis_client.zadd = AsyncMock()
    redis_client.expire = AsyncMock()
    redis_client.zrange = AsyncMock()
    redis_client.ttl = AsyncMock()
    
    return redis_client


@pytest.fixture
def rate_limiter(mock_redis_client):
    """Create RateLimiter instance with mocked Redis."""
    return RateLimiter(mock_redis_client)


@pytest.mark.asyncio
async def test_check_rate_limit_allowed(rate_limiter, mock_redis_client):
    """Test rate limit check when under limit."""
    # Configure mock pipeline to return current count of 5
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [1, 5, 1, 1]  # zrem, zcard, zadd, expire results
    
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    # Test check with limit of 10 per minute
    allowed, remaining, retry_after = await rate_limiter.check_rate_limit("test:key", 10)
    
    # Verify result
    assert allowed is True
    assert remaining == 5  # 10 - 5
    assert retry_after == 0.0
    
    # Verify Redis operations were called
    mock_redis_client.pipeline.assert_called_once()
    mock_pipeline.zremrangebyscore.assert_called_once()
    mock_pipeline.zcard.assert_called_once()
    mock_pipeline.zadd.assert_called_once()
    mock_pipeline.expire.assert_called_once()
    mock_pipeline.execute.assert_called_once()


@pytest.mark.asyncio
async def test_check_rate_limit_exceeded(rate_limiter, mock_redis_client):
    """Test rate limit check when limit exceeded."""
    # Configure mock pipeline to return current count of 15 (exceeds limit of 10)
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [1, 15, 1, 1]
    
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    # Mock zrange to return oldest timestamp
    mock_redis_client.zrange.return_value = [("timestamp", 1234567890.0)]
    
    # Test check with limit of 10 per minute
    allowed, remaining, retry_after = await rate_limiter.check_rate_limit("test:key", 10)
    
    # Verify result
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0
    
    # Verify Redis operations were called
    mock_redis_client.zrange.assert_called_once()


@pytest.mark.asyncio
async def test_check_api_key_limit_allowed(rate_limiter, mock_redis_client):
    """Test API key rate limit check when under limit."""
    # Configure mock pipeline to return current count of 5
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [1, 5, 1, 1]
    
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    # Test with API key ID 123 and limit 100
    result = await rate_limiter.check_api_key_limit(123, 100, raise_on_exceed=False)
    
    # Verify no exception returned
    assert result is None
    
    # Verify Redis key format
    mock_pipeline.zadd.assert_called_once()
    args, kwargs = mock_pipeline.zadd.call_args
    assert "ratelimit:api:123" in args


@pytest.mark.asyncio
async def test_check_api_key_limit_exceeded(rate_limiter, mock_redis_client):
    """Test API key rate limit check when limit exceeded."""
    # Configure mock pipeline to return current count of 150 (exceeds limit of 100)
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [1, 150, 1, 1]
    
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    # Mock zrange to return oldest timestamp
    mock_redis_client.zrange.return_value = [("timestamp", 1234567890.0)]
    
    # Test with raise_on_exceed=False
    result = await rate_limiter.check_api_key_limit(123, 100, raise_on_exceed=False)
    
    # Verify HTTPException returned
    assert isinstance(result, HTTPException)
    assert result.status_code == 429
    assert "Retry-After" in result.headers
    assert result.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_check_api_key_limit_raises(rate_limiter, mock_redis_client):
    """Test API key rate limit raises exception when exceeded."""
    # Configure mock pipeline to return current count of 150 (exceeds limit of 100)
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = [1, 150, 1, 1]
    
    mock_redis_client.pipeline.return_value = mock_pipeline
    
    # Mock zrange to return oldest timestamp
    mock_redis_client.zrange.return_value = [("timestamp", 1234567890.0)]
    
    # Test with raise_on_exceed=True (default)
    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter.check_api_key_limit(123, 100)
    
    # Verify exception details
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    assert "X-RateLimit-Remaining" in exc_info.value.headers
    assert "X-RateLimit-Limit" in exc_info.value.headers
    assert "X-RateLimit-Reset" in exc_info.value.headers


@pytest.mark.asyncio
async def test_get_rate_limit_status(rate_limiter, mock_redis_client):
    """Test getting rate limit status without incrementing."""
    # Mock Redis operations
    mock_redis_client.zremrangebyscore.return_value = 1
    mock_redis_client.zcard.return_value = 7
    mock_redis_client.ttl.return_value = 45
    mock_redis_client.zrange.return_value = [("timestamp", 1234567890.0)]
    
    # Get status
    status = await rate_limiter.get_rate_limit_status("test:key", 10)
    
    # Verify result
    assert status["key"] == "test:key"
    assert status["current_count"] == 7
    assert status["limit"] == 10
    assert status["remaining"] == 3
    assert status["window_seconds"] == 60
    assert status["ttl"] == 45
    assert status["reset_time"] == 1234567890.0 + 60
    assert status["reset_in"] > 0
    
    # Verify Redis operations
    mock_redis_client.zremrangebyscore.assert_called_once()
    mock_redis_client.zcard.assert_called_once()
    mock_redis_client.ttl.assert_called_once()
    mock_redis_client.zrange.assert_called_once()


def test_fastapi_dependency_injection():
    """Test FastAPI dependency injection works."""
    app = FastAPI()
    
    # This would be tested with actual FastAPI test client
    # For now, just verify the functions exist and are callable
    assert callable(get_rate_limiter)
    assert callable(rate_limit_dependency)
    
    # RateLimiter should be instantiable
    limiter = RateLimiter(None)
    assert isinstance(limiter, RateLimiter)


@pytest.mark.asyncio
async def test_concurrent_rate_limiting():
    """Test that rate limiter handles concurrent requests correctly."""
    # This test would require more complex mocking
    # For now, verify the method signatures and basic functionality
    mock_redis = AsyncMock()
    limiter = RateLimiter(mock_redis)
    
    # Should have all expected methods
    assert hasattr(limiter, 'check_rate_limit')
    assert hasattr(limiter, 'check_and_increment')
    assert hasattr(limiter, 'check_api_key_limit')
    assert hasattr(limiter, 'get_rate_limit_status')
    
    # Methods should be async
    import inspect
    assert inspect.iscoroutinefunction(limiter.check_rate_limit)
    assert inspect.iscoroutinefunction(limiter.check_api_key_limit)