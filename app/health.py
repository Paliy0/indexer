"""
Health check endpoints for monitoring and readiness.

Provides:
- /health: Liveness probe (always returns OK if service is running)
- /ready: Readiness probe (checks database, Redis, Meilisearch connectivity)
- /metrics: Prometheus metrics endpoint
"""

import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as aioredis
import httpx
import logging
from prometheus_client import generate_latest
from prometheus_client import generate_latest

from app.config import get_settings
from app.db import get_db
from app.meilisearch_engine import MeiliSearchEngine

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


async def check_postgres(db: AsyncSession) -> Dict[str, Any]:
    """Check PostgreSQL connectivity."""
    try:
        start_time = time.time()
        result = await db.execute(text("SELECT 1"))
        await result.fetchone()
        latency_ms = (time.time() - start_time) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def check_redis() -> Dict[str, Any]:
    """Check Redis connectivity."""
    try:
        start_time = time.time()
        redis_client = await aioredis.from_url("redis://localhost:6379/0")
        await redis_client.ping()
        latency_ms = (time.time() - start_time) * 1000
        await redis_client.close()
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2)
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


async def check_meilisearch() -> Dict[str, Any]:
    """Check Meilisearch connectivity."""
    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.meilisearch_host}/health")
            latency_ms = (time.time() - start_time) * 1000
            if response.status_code == 200:
                health_data = response.json()
                return {
                    "status": health_data.get("status", "healthy"),
                    "latency_ms": round(latency_ms, 2),
                    "details": health_data
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "latency_ms": round(latency_ms, 2)
                }
    except Exception as e:
        logger.error(f"Meilisearch health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/health", response_class=JSONResponse)
async def health_check() -> Dict[str, str]:
    """
    Liveness probe endpoint.
    
    Always returns OK if the service is running.
    This endpoint should have minimal dependencies and not check external services.
    """
    return {"status": "ok"}


@router.get("/ready", response_class=JSONResponse)
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    detailed: bool = False
) -> Dict[str, Any]:
    """
    Readiness probe endpoint.
    
    Checks connectivity to all dependent services:
    - PostgreSQL database
    - Redis (for caching and Celery)
    - Meilisearch (for search)
    
    Returns:
        - 200 OK with component status if all services are healthy
        - 503 Service Unavailable if any service is unhealthy
        
    Query parameters:
        - detailed: If true, include detailed component status in response
    """
    component_checks = {}
    all_healthy = True
    
    # Check PostgreSQL
    pg_result = await check_postgres(db)
    component_checks["postgresql"] = pg_result
    if pg_result["status"] != "healthy":
        all_healthy = False
    
    # Check Redis (only if Redis is configured)
    try:
        redis_result = await check_redis()
        component_checks["redis"] = redis_result
        if redis_result["status"] != "healthy":
            all_healthy = False
    except Exception as e:
        logger.warning(f"Redis check failed: {e}")
        component_checks["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        all_healthy = False
    
    # Check Meilisearch (only if Meilisearch is configured)
    try:
        meili_result = await check_meilisearch()
        component_checks["meilisearch"] = meili_result
        if meili_result["status"] != "healthy":
            all_healthy = False
    except Exception as e:
        logger.warning(f"Meilisearch check failed: {e}")
        component_checks["meilisearch"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        all_healthy = False
    
    response_data = {
        "status": "ready" if all_healthy else "not_ready",
        "timestamp": time.time()
    }
    
    if detailed:
        response_data["components"] = component_checks
    
    if not all_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data
        )
    
    return response_data


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint() -> str:
    """
    Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text exposition format.
    """
    # Generate Prometheus metrics from all registered collectors
    metrics_data = generate_latest()
    return metrics_data.decode('utf-8')