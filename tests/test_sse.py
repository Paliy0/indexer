"""
Tests for Server-Sent Events (SSE) progress endpoint.

Simple tests that verify SSE endpoint exists and returns proper format.
Full integration testing with Redis is done in integration tests.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.responses import StreamingResponse


@pytest.mark.asyncio
async def test_sse_endpoint_returns_streaming_response():
    """Test that SSE endpoint returns a StreamingResponse."""
    
    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={
        b"pages_found": b"1",
        b"current_url": b"",
        b"status": b"completed",
        b"updated_at": b"2024-01-01T12:00:00"
    })
    
    async def mock_from_url(url):
        return mock_redis
    
    with patch("app.main.aioredis.from_url", side_effect=mock_from_url):
        from app.main import app
        
        # Find endpoint
        endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and '/progress/stream' in route.path:
                endpoint = route.endpoint
                break
        
        assert endpoint is not None
        
        # Call endpoint
        response = await endpoint(site_id=1)
        
        # Verify it's a StreamingResponse
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_sse_response_has_correct_headers():
    """Test SSE response includes correct headers for streaming."""
    
    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={
        b"pages_found": b"1",
        b"current_url": b"",
        b"status": b"completed",
        b"updated_at": b"2024-01-01T12:00:00"
    })
    
    async def mock_from_url(url):
        return mock_redis
    
    with patch("app.main.aioredis.from_url", side_effect=mock_from_url):
        from app.main import app
        
        # Find endpoint
        endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and '/progress/stream' in route.path:
                endpoint = route.endpoint
                break
        
        response = await endpoint(site_id=1)
        
        # Check headers
        assert "cache-control" in response.headers
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["connection"] == "keep-alive"
        assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.asyncio
async def test_sse_event_stream_format():
    """Test that SSE events are properly formatted."""
    import json
    
    # Mock Redis
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={
        b"pages_found": b"5",
        b"current_url": b"https://example.com",
        b"status": b"completed",
        b"updated_at": b"2024-01-01T12:00:00"
    })
    
    async def mock_from_url(url):
        return mock_redis
    
    with patch("app.main.aioredis.from_url", side_effect=mock_from_url):
        from app.main import app
        
        # Find endpoint
        endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and '/progress/stream' in route.path:
                endpoint = route.endpoint
                break
        
        response = await endpoint(site_id=1)
        
        # Get first event from stream
        async for chunk in response.body_iterator:
            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk
            
            # Verify SSE format: "data: {json}\n\n"
            assert chunk_str.startswith('data: ')
            assert '\n\n' in chunk_str
            
            # Extract and parse JSON
            json_part = chunk_str.split('\n\n')[0][6:]  # Remove "data: " prefix
            event_data = json.loads(json_part)
            
            # Verify event structure
            assert "pages_found" in event_data
            assert "current_url" in event_data
            assert "status" in event_data
            assert event_data["pages_found"] == 5
            assert event_data["status"] == "completed"
            
            break  # Only check first event


@pytest.mark.asyncio
async def test_sse_stream_closes_on_completion():
    """Test that SSE stream closes when status is completed."""
    import json
    
    # Mock Redis to return completed status
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={
        b"pages_found": b"10",
        b"current_url": b"",
        b"status": b"completed",
        b"updated_at": b"2024-01-01T12:00:00"
    })
    
    async def mock_from_url(url):
        return mock_redis
    
    with patch("app.main.aioredis.from_url", side_effect=mock_from_url):
        from app.main import app
        
        # Find endpoint
        endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and '/progress/stream' in route.path:
                endpoint = route.endpoint
                break
        
        response = await endpoint(site_id=1)
        
        # Collect all events (should only be one for completed)
        events = []
        async for chunk in response.body_iterator:
            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk
            if chunk_str.startswith('data: '):
                json_part = chunk_str.split('\n\n')[0][6:]
                event_data = json.loads(json_part)
                events.append(event_data)
        
        # Should have received one event with done=True
        assert len(events) == 1
        assert events[0]["status"] == "completed"
        assert events[0].get("done") is True


@pytest.mark.asyncio
async def test_sse_stream_closes_on_failure():
    """Test that SSE stream closes when status is failed."""
    import json
    
    # Mock Redis to return failed status
    mock_redis = AsyncMock()
    mock_redis.close = AsyncMock()
    mock_redis.hgetall = AsyncMock(return_value={
        b"pages_found": b"3",
        b"current_url": b"",
        b"status": b"failed",
        b"updated_at": b"2024-01-01T12:00:00"
    })
    
    async def mock_from_url(url):
        return mock_redis
    
    with patch("app.main.aioredis.from_url", side_effect=mock_from_url):
        from app.main import app
        
        # Find endpoint
        endpoint = None
        for route in app.routes:
            if hasattr(route, 'path') and '/progress/stream' in route.path:
                endpoint = route.endpoint
                break
        
        response = await endpoint(site_id=1)
        
        # Collect all events
        events = []
        async for chunk in response.body_iterator:
            chunk_str = chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk
            if chunk_str.startswith('data: '):
                json_part = chunk_str.split('\n\n')[0][6:]
                event_data = json.loads(json_part)
                events.append(event_data)
        
        # Should have one event with failed status and done=True
        assert len(events) == 1
        assert events[0]["status"] == "failed"
        assert events[0].get("done") is True
