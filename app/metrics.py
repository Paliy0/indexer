"""
Prometheus metrics for the Site Search Platform.
"""
from prometheus_client import Counter, Histogram, Gauge
from prometheus_client.core import REGISTRY
import time
from typing import Optional, Callable
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

# HTTP metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Search metrics
search_queries_total = Counter(
    'search_queries_total',
    'Total search queries',
    ['site_id']
)

# Scraping metrics
scrape_jobs_total = Counter(
    'scrape_jobs_total',
    'Total scrape jobs',
    ['status']  # started, completed, failed
)

scrape_duration_seconds = Histogram(
    'scrape_duration_seconds',
    'Scrape job duration in seconds',
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)
)

active_scrapes = Gauge(
    'active_scrapes',
    'Number of currently active scrape jobs'
)

# Database metrics
db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections'
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically track HTTP requests with Prometheus metrics.
    """
    
    def __init__(self, app, skip_paths: Optional[list] = None):
        super().__init__(app)
        self.skip_paths = skip_paths or ['/health', '/ready', '/metrics']
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip metrics endpoints to avoid infinite recursion
        path = request.url.path
        if any(path.startswith(skip_path) for skip_path in self.skip_paths):
            return await call_next(request)
        
        # Record start time for duration measurement
        start_time = time.time()
        
        try:
            response = await call_next(request)
        except Exception as e:
            # Track failed requests
            http_requests_total.labels(
                method=request.method,
                endpoint=self._sanitize_endpoint(path),
                status='500'
            ).inc()
            
            # Record duration even for failed requests
            duration = time.time() - start_time
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=self._sanitize_endpoint(path)
            ).observe(duration)
            
            raise e
        
        # Record successful request
        http_requests_total.labels(
            method=request.method,
            endpoint=self._sanitize_endpoint(path),
            status=str(response.status_code)
        ).inc()
        
        # Record request duration
        duration = time.time() - start_time
        http_request_duration_seconds.labels(
            method=request.method,
            endpoint=self._sanitize_endpoint(path)
        ).observe(duration)
        
        return response
    
    def _sanitize_endpoint(self, path: str) -> str:
        """
        Sanitize path to create meaningful endpoint labels.
        Replaces dynamic parts with placeholders.
        """
        # Handle common patterns
        path = path.rstrip('/')
        
        # Replace UUIDs and IDs with placeholders
        import re
        
        # Site IDs: /api/sites/{site_id}
        path = re.sub(r'/sites/[0-9a-fA-F\-]+', '/sites/{site_id}', path)
        
        # Page IDs: /api/pages/{page_id}
        path = re.sub(r'/pages/[0-9a-fA-F\-]+', '/pages/{page_id}', path)
        
        # Domain patterns in subdomain routing
        path = re.sub(r'^/[a-zA-Z0-9\-\.]+/', '/{subdomain}/', path)
        
        # API keys in query params (remove)
        if '?' in path:
            path = path.split('?')[0]
        
        return path


def increment_search_query(site_id: Optional[int] = None):
    """
    Increment search query counter.
    """
    site_label = str(site_id) if site_id else 'none'
    search_queries_total.labels(site_id=site_label).inc()


def track_scrape_start():
    """
    Track the start of a scrape job.
    """
    scrape_jobs_total.labels(status='started').inc()
    active_scrapes.inc()
    return time.time()


def track_scrape_complete(start_time: float):
    """
    Track the completion of a scrape job.
    """
    scrape_jobs_total.labels(status='completed').inc()
    active_scrapes.dec()
    
    duration = time.time() - start_time
    scrape_duration_seconds.observe(duration)


def track_scrape_failed(start_time: float):
    """
    Track a failed scrape job.
    """
    scrape_jobs_total.labels(status='failed').inc()
    active_scrapes.dec()
    
    duration = time.time() - start_time
    scrape_duration_seconds.observe(duration)


def update_db_connections(count: int):
    """
    Update the active database connections gauge.
    """
    db_connections_active.set(count)


def get_metrics_registry():
    """
    Get the Prometheus registry.
    """
    return REGISTRY