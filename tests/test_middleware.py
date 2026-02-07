"""
Tests for SubdomainMiddleware.

Tests subdomain extraction from various Host headers:
- subdomain.example.com -> subdomain extracted
- localhost -> no subdomain
- 127.0.0.1 -> no subdomain
- IP addresses -> no subdomain
- Bare domain -> no subdomain
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.middleware import SubdomainMiddleware


def create_test_app(base_domain=None):
    """Create a test FastAPI app with subdomain middleware."""
    app = FastAPI()
    
    # Add subdomain middleware
    app.add_middleware(SubdomainMiddleware, base_domain=base_domain)
    
    @app.get("/")
    async def root(request: Request):
        """Test endpoint that returns subdomain state."""
        return JSONResponse({
            "subdomain": request.state.subdomain,
            "is_subdomain": request.state.is_subdomain
        })
    
    return app


def test_subdomain_extraction():
    """Test subdomain is correctly extracted from Host header."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "mysite.example.com"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] == "mysite"
    assert data["is_subdomain"] is True


def test_subdomain_with_port():
    """Test subdomain extraction when port is included in Host header."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "mysite.example.com:8000"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] == "mysite"
    assert data["is_subdomain"] is True


def test_localhost_no_subdomain():
    """Test localhost is treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "localhost"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_localhost_with_port_no_subdomain():
    """Test localhost:8000 is treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "localhost:8000"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_loopback_ip_no_subdomain():
    """Test 127.0.0.1 is treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "127.0.0.1"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_loopback_ip_with_port_no_subdomain():
    """Test 127.0.0.1:8000 is treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_private_ip_no_subdomain():
    """Test private IP addresses are treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    # Test various private IP ranges
    for ip in ["192.168.1.1", "10.0.0.1", "172.16.0.1"]:
        response = client.get("/", headers={"Host": ip})
        assert response.status_code == 200
        
        data = response.json()
        assert data["subdomain"] is None
        assert data["is_subdomain"] is False


def test_bare_domain_no_subdomain():
    """Test bare domain (no subdomain) is correctly identified."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "example.com"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_bare_domain_with_port_no_subdomain():
    """Test bare domain with port is correctly identified."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "example.com:8000"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_subdomain_with_hyphens():
    """Test subdomain with hyphens is correctly extracted."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "my-site-123.example.com"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] == "my-site-123"
    assert data["is_subdomain"] is True


def test_subdomain_case_insensitive():
    """Test subdomain extraction is case-insensitive."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": "MySite.EXAMPLE.COM"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] == "mysite"
    assert data["is_subdomain"] is True


def test_www_subdomain_not_matched():
    """Test that www or other non-matching patterns are treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    # www.example.com should match as subdomain "www"
    response = client.get("/", headers={"Host": "www.example.com"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] == "www"
    assert data["is_subdomain"] is True


def test_invalid_host_no_subdomain():
    """Test invalid host patterns are treated as no subdomain."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    # Different domain entirely
    response = client.get("/", headers={"Host": "different.org"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_no_base_domain_configured():
    """Test middleware behavior when no base_domain is configured."""
    app = create_test_app(base_domain=None)
    client = TestClient(app)
    
    # Should not extract subdomain if base_domain is None
    response = client.get("/", headers={"Host": "mysite.example.com"})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_empty_host_header():
    """Test behavior with empty Host header."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    response = client.get("/", headers={"Host": ""})
    assert response.status_code == 200
    
    data = response.json()
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_multi_level_subdomain():
    """Test that multi-level subdomains (e.g., a.b.example.com) are not matched."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    # a.b.example.com should not match the pattern (only single-level subdomains)
    response = client.get("/", headers={"Host": "a.b.example.com"})
    assert response.status_code == 200
    
    data = response.json()
    # This won't match the pattern because we only match single-level subdomains
    assert data["subdomain"] is None
    assert data["is_subdomain"] is False


def test_subdomain_alphanumeric():
    """Test subdomain with alphanumeric characters."""
    app = create_test_app(base_domain="example.com")
    client = TestClient(app)
    
    for subdomain in ["site1", "abc123", "test-site-99"]:
        response = client.get("/", headers={"Host": f"{subdomain}.example.com"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["subdomain"] == subdomain
        assert data["is_subdomain"] is True
