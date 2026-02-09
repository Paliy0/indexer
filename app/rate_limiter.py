"""
Redis-based rate limiting using sliding window algorithm.

Provides:
- RateLimiter class for checking rate limits with Redis sorted sets
- FastAPI dependency that integrates with API key authentication
- Returns 429 responses with proper headers when limit exceeded

Usage:
    rate_limiter = RateLimiter(redis_client)
    allowed, remaining, retry_after = await rate_limiter.check_rate_limit("key", 100)
    
    # FastAPI dependency:
    @app.get("/api/endpoint")
    async def endpoint(rate_limiter: RateLimiter = Depends(get_rate_limiter)):
        await rate_limiter.check_api_key_limit(api_key_id)
"""

import redis.asyncio as aioredis
from datetime import datetime, timedelta, UTC, UTC
from typing import Tuple, Optional
from fastapi import Depends, HTTPException
import time


class RateLimiter:
    """Redis-based rate limiter using sliding window algorithm."""
    
    def __init__(self, redis_client: aioredis.Redis):
        """
        Initialize rate limiter with Redis client.
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
    
    async def check_rate_limit(
        self,
        key: str,
        limit_per_minute: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int, float]:
        """
        Check if request is within rate limit using Redis sorted set.
        
        Args:
            key: Unique identifier for the rate limit (e.g., api:123)
            limit_per_minute: Maximum requests per minute
            window_seconds: Time window in seconds (default: 60)
            
        Returns:
            Tuple of (allowed: bool, remaining: int, retry_after: float)
            - allowed: Whether request is allowed
            - remaining: Number of requests remaining in current window
            - retry_after: Seconds until next request is allowed (if not allowed)
        """
        now = datetime.now(UTC)
        now_ts = now.timestamp()
        window_start_ts = now_ts - window_seconds
        
        redis_key = f"ratelimit:{key}"
        
        # Use pipeline for atomic operations
        pipe = await self.redis.pipeline()
        
        # Remove requests older than the window
        await pipe.zremrangebyscore(redis_key, 0, window_start_ts)
        
        # Count current requests in window
        await pipe.zcard(redis_key)
        
        # Add current request timestamp
        await pipe.zadd(redis_key, {str(now_ts): now_ts})
        
        # Set expiry on the key (clean up after window passes)
        await pipe.expire(redis_key, window_seconds)
        
        # Execute pipeline
        results = await pipe.execute()
        current_count = results[1]  # Result of zcard
        
        remaining = max(0, limit_per_minute - current_count)
        
        if current_count >= limit_per_minute:
            # Calculate retry time
            oldest_entry = await self.redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest_entry:
                oldest_ts = oldest_entry[0][1]
                retry_after = oldest_ts + window_seconds - now_ts
            else:
                retry_after = window_seconds
            
            return False, 0, max(0, retry_after)
        
        return True, remaining, 0.0
    
    async def check_and_increment(
        self,
        key: str,
        limit_per_minute: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int, float]:
        """
        Alias for check_rate_limit for backward compatibility.
        """
        return await self.check_rate_limit(key, limit_per_minute, window_seconds)
    
    async def check_api_key_limit(
        self,
        api_key_id: int,
        limit_per_minute: int,
        raise_on_exceed: bool = True
    ) -> Optional[HTTPException]:
        """
        Check rate limit for an API key.
        
        Args:
            api_key_id: API key ID
            limit_per_minute: Rate limit for this key
            raise_on_exceed: Whether to raise HTTPException when limit exceeded
            
        Returns:
            HTTPException if limit exceeded and raise_on_exceed=False, None otherwise
            
        Raises:
            HTTPException: 429 with Retry-After and X-RateLimit-Remaining headers
        """
        key = f"api:{api_key_id}"
        allowed, remaining, retry_after = await self.check_rate_limit(
            key, limit_per_minute
        )
        
        if not allowed:
            if raise_on_exceed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again in {int(retry_after)} seconds.",
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Limit": str(limit_per_minute),
                        "X-RateLimit-Reset": str(int(time.time() + retry_after))
                    }
                )
            else:
                return HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "Retry-After": str(int(retry_after)),
                        "X-RateLimit-Remaining": "0"
                    }
                )
        
        return None
    
    async def get_rate_limit_status(
        self,
        key: str,
        limit_per_minute: int,
        window_seconds: int = 60
    ) -> dict:
        """
        Get current rate limit status without incrementing counter.
        
        Args:
            key: Rate limit key
            limit_per_minute: Limit for the key
            window_seconds: Time window in seconds
            
        Returns:
            Dictionary with limit status
        """
        now = datetime.now(UTC)
        now_ts = now.timestamp()
        window_start_ts = now_ts - window_seconds
        
        redis_key = f"ratelimit:{key}"
        
        # Remove old entries
        await self.redis.zremrangebyscore(redis_key, 0, window_start_ts)
        
        # Count current entries
        current_count = await self.redis.zcard(redis_key)
        
        # Get TTL
        ttl = await self.redis.ttl(redis_key)
        
        # Calculate when window resets
        reset_time = None
        if current_count > 0:
            oldest_entry = await self.redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest_entry:
                reset_time = int(oldest_entry[0][1] + window_seconds)
        
        return {
            "key": key,
            "current_count": current_count,
            "limit": limit_per_minute,
            "remaining": max(0, limit_per_minute - current_count),
            "window_seconds": window_seconds,
            "ttl": ttl,
            "reset_time": reset_time,
            "reset_in": reset_time - now_ts if reset_time else 0
        }


async def get_redis_client() -> aioredis.Redis:
    """
    Get Redis client instance.
    
    Returns:
        Async Redis client connected to local Redis instance
    """
    return await aioredis.from_url("redis://localhost:6379/0")


async def get_rate_limiter() -> RateLimiter:
    """
    FastAPI dependency to get RateLimiter instance.
    
    Returns:
        RateLimiter instance with Redis client
    """
    redis_client = await get_redis_client()
    return RateLimiter(redis_client)


# Rate limiting dependency for FastAPI endpoints
async def rate_limit_dependency(
    api_key_id: int,
    limit_per_minute: int,
    rate_limiter: RateLimiter = Depends(get_rate_limiter)
):
    """
    FastAPI dependency that checks rate limit for an API key.
    
    Usage:
        @app.get("/api/endpoint")
        async def endpoint(
            api_key: APIKey = Depends(verify_api_key),
            _ = Depends(rate_limit_dependency, api_key_id=api_key.id, limit_per_minute=api_key.rate_limit_per_minute)
        ):
            # Proceed if rate limit not exceeded
            pass
    """
    await rate_limiter.check_api_key_limit(api_key_id, limit_per_minute)