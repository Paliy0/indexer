"""
Middleware for handling subdomain extraction and routing.

Usage:
    1. Set BASE_DOMAIN in .env (e.g., BASE_DOMAIN=example.com)
    2. Configure wildcard DNS: *.example.com -> your server IP
    3. Access sites via subdomains: sitename.example.com
    
    The middleware will extract 'sitename' and set:
        - request.state.subdomain = "sitename"
        - request.state.is_subdomain = True
    
    The root endpoint (/) will then route to the appropriate page based on site status:
        - Site not found: Setup/scrape page
        - Site status=scraping: Progress page
        - Site status=completed: Search page
        - Site status=failed/pending: Status page
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import re
from typing import Callable, Optional


class SubdomainMiddleware(BaseHTTPMiddleware):
    """
    Extract subdomain from request Host header and add to request state.
    
    Sets:
        request.state.subdomain: The extracted subdomain (str or None)
        request.state.is_subdomain: Whether a subdomain was detected (bool)
    
    Handles special cases:
        - localhost (no subdomain)
        - 127.0.0.1 (no subdomain)
        - IP addresses (no subdomain)
        - Bare domain (no subdomain)
        - Subdomain.domain (subdomain detected)
    """
    
    def __init__(self, app, base_domain: Optional[str] = None):
        """
        Initialize subdomain middleware.
        
        Args:
            app: The ASGI application
            base_domain: The base domain to match against (e.g., "example.com")
                        If None, subdomain detection is disabled
        """
        super().__init__(app)
        self.base_domain = base_domain
        
        # Compile regex patterns for performance
        # Match IPv4 addresses (e.g., 127.0.0.1, 192.168.1.1)
        self.ip_pattern = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
        
        # Match subdomain pattern if base_domain is provided
        if self.base_domain:
            # Pattern matches: subdomain.base_domain
            # Allows alphanumeric and hyphens in subdomain
            escaped_domain = re.escape(self.base_domain)
            self.subdomain_pattern = re.compile(
                rf'^([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)\.{escaped_domain}$'
            )
        else:
            self.subdomain_pattern = None
    
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and extract subdomain information.
        
        Args:
            request: The incoming request
            call_next: The next middleware or endpoint handler
            
        Returns:
            Response from the next handler
        """
        # Get host from header and strip port if present
        host = request.headers.get("host", "").lower()
        
        # Remove port number (e.g., localhost:8000 -> localhost)
        if ":" in host:
            host = host.split(":")[0]
        
        # Initialize state
        request.state.subdomain = None
        request.state.is_subdomain = False
        
        # Skip subdomain detection if base_domain not configured
        if not self.base_domain:
            response = await call_next(request)
            return response
        
        # Check for special cases (no subdomain)
        if (
            host == "localhost"
            or host == "127.0.0.1"
            or self.ip_pattern.match(host)
            or host == self.base_domain
        ):
            # These are treated as non-subdomain requests
            request.state.subdomain = None
            request.state.is_subdomain = False
        elif self.subdomain_pattern:
            # Try to match subdomain pattern
            match = self.subdomain_pattern.match(host)
            if match:
                subdomain = match.group(1)
                request.state.subdomain = subdomain
                request.state.is_subdomain = True
            else:
                # Host doesn't match expected pattern
                # Treat as non-subdomain (could be www or other prefix)
                request.state.subdomain = None
                request.state.is_subdomain = False
        
        # Continue processing request
        response = await call_next(request)
        return response
