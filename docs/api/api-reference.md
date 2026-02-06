# API Reference

## Overview

The Site Search API provides programmatic access to the platform's core functionality. 

**Base URL:** `https://api.yourdomain.com` (or `https://yourdomain.com/api`)

**Authentication:** API Key via `Authorization: Bearer <token>` header

**Content-Type:** `application/json`

**Version:** `v1`

---

## Authentication

### API Key Format
```
Authorization: Bearer ss_<64-character-token>
```

### Response Codes
| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Invalid or missing API key |
| 403 | Forbidden | Valid key but insufficient permissions |
| 404 | Not Found | Resource does not exist |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

### Rate Limiting
- Default: 100 requests per minute per API key
- Headers returned with every response:
  - `X-RateLimit-Limit`: Request limit
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Unix timestamp when limit resets

---

## Endpoints

### Sites

#### List Sites
```http
GET /api/v1/sites
```

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| skip | integer | No | 0 | Number of sites to skip |
| limit | integer | No | 20 | Number of sites to return (max 100) |
| status | string | No | - | Filter by status: pending, scraping, completed, failed |

**Response (200 OK):**
```json
{
  "sites": [
    {
      "id": 1,
      "url": "https://fitgirl-repacks.site",
      "domain": "fitgirl-repacks.site",
      "status": "completed",
      "page_count": 658,
      "last_scraped": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

---

#### Create Site
```http
POST /api/v1/sites
```

**Request Body:**
```json
{
  "url": "https://example.com",
  "crawl": true,
  "max_depth": 2,
  "config": {
    "content_selector": "article",
    "exclude_selectors": [".ads", ".sidebar"]
  }
}
```

**Parameters:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| url | string | Yes | - | Website URL to index |
| crawl | boolean | No | true | Enable recursive crawling |
| max_depth | integer | No | 2 | Maximum crawl depth (1-5) |
| config | object | No | {} | Site configuration (see below) |

**Response (202 Accepted):**
```json
{
  "site_id": 2,
  "url": "https://example.com",
  "status": "scraping",
  "message": "Scraping started",
  "estimated_completion": "2024-01-15T10:05:00Z"
}
```

**Error Response (400 Bad Request):**
```json
{
  "error": "Invalid URL format",
  "details": "URL must start with http:// or https://"
}
```

---

#### Get Site
```http
GET /api/v1/sites/{site_id}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "url": "https://fitgirl-repacks.site",
  "domain": "fitgirl-repacks.site",
  "status": "completed",
  "page_count": 658,
  "config": {
    "content_selector": "article",
    "max_depth": 2,
    "auto_reindex": false
  },
  "last_scraped": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-15T10:00:00Z"
}
```

---

#### Update Site Configuration
```http
PATCH /api/v1/sites/{site_id}/config
```

**Request Body:**
```json
{
  "content_selector": ".main-content",
  "exclude_selectors": [".ads", ".comments"],
  "max_depth": 3,
  "auto_reindex": true,
  "reindex_interval_days": 7
}
```

**Config Fields:**
| Field | Type | Description |
|-------|------|-------------|
| content_selector | string | CSS selector for main content |
| title_selector | string | CSS selector for page title |
| exclude_selectors | array | CSS selectors to exclude |
| max_depth | integer | Maximum crawl depth (1-5) |
| delay_ms | integer | Delay between requests (50-5000) |
| include_patterns | array | Regex patterns to include |
| exclude_patterns | array | Regex patterns to exclude |
| auto_reindex | boolean | Enable scheduled re-indexing |
| reindex_interval_days | integer | Days between re-indexes (1-30) |

**Response (200 OK):**
```json
{
  "message": "Configuration updated",
  "config": { ... }
}
```

---

#### Delete Site
```http
DELETE /api/v1/sites/{site_id}
```

**Response (204 No Content)**

---

#### Re-index Site
```http
POST /api/v1/sites/{site_id}/reindex
```

**Response (202 Accepted):**
```json
{
  "site_id": 1,
  "status": "scraping",
  "message": "Re-indexing started"
}
```

---

#### Get Scraping Progress
```http
GET /api/v1/sites/{site_id}/progress
```

**Response (200 OK) - While scraping:**
```json
{
  "site_id": 1,
  "status": "scraping",
  "pages_found": 45,
  "current_url": "https://example.com/page-45",
  "percent_complete": 68,
  "started_at": "2024-01-15T10:00:00Z",
  "estimated_completion": "2024-01-15T10:05:00Z"
}
```

**Response (200 OK) - Completed:**
```json
{
  "site_id": 1,
  "status": "completed",
  "pages_found": 658,
  "completed_at": "2024-01-15T10:30:00Z",
  "duration_seconds": 1800
}
```

---

#### Preview Selector
```http
POST /api/v1/sites/{site_id}/preview
```

**Request Body:**
```json
{
  "content_selector": ".article-content"
}
```

**Response (200 OK):**
```json
{
  "elements_found": 5,
  "preview": "<div class='article-content'>...</div>",
  "sample_url": "https://example.com/sample-page"
}
```

---

### Search

#### Search Pages
```http
GET /api/v1/search
```

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| q | string | Yes | - | Search query |
| site_id | integer | No | - | Filter by site ID |
| limit | integer | No | 20 | Results per page (1-100) |
| offset | integer | No | 0 | Pagination offset |
| highlight | boolean | No | true | Highlight matching terms |

**Response (200 OK):**
```json
{
  "query": "repack",
  "total_hits": 45,
  "processing_time_ms": 23,
  "hits": [
    {
      "id": "1_123",
      "site_id": 1,
      "url": "https://fitgirl-repacks.site/game-title/",
      "title": "Game Title <mark>Repack</mark>",
      "snippet": "This is a <mark>repack</mark> of the game with all DLC included...",
      "rank": 0.95
    }
  ]
}
```

**Search Features:**
- Typo tolerance (e.g., "instalation" → "installation")
- Stemming (e.g., "running" matches "run")
- Stop words automatically ignored
- Results ranked by relevance

---

#### Search Suggestions
```http
GET /api/v1/search/suggest
```

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| q | string | Yes | - | Partial query |
| site_id | integer | No | - | Filter by site |
| limit | integer | No | 5 | Max suggestions (1-10) |

**Response (200 OK):**
```json
{
  "query": "instal",
  "suggestions": [
    "installation",
    "install",
    "installing"
  ]
}
```

---

### Export

#### Export Site Data
```http
GET /api/v1/sites/{site_id}/export
```

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| format | string | No | json | Export format: json, csv, md |
| include_content | boolean | No | true | Include full page content |

**Response (200 OK) - JSON:**
```json
{
  "exported_at": "2024-01-15T12:00:00Z",
  "site": {
    "id": 1,
    "url": "https://fitgirl-repacks.site"
  },
  "total_pages": 658,
  "pages": [
    {
      "url": "https://fitgirl-repacks.site/game-title/",
      "title": "Game Title Repack",
      "content": "...",
      "indexed_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Response (200 OK) - CSV:**
```csv
url,title,content_preview,indexed_at
https://fitgirl-repacks.site/game-title/,Game Title Repack,This is a repack...,2024-01-15T10:30:00Z
```

**Response Headers (CSV):**
```
Content-Type: text/csv
Content-Disposition: attachment; filename="site-1-export.csv"
```

---

### Analytics

#### Get Search Analytics
```http
GET /api/v1/sites/{site_id}/analytics
```

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| days | integer | No | 30 | Time period (1-90) |

**Response (200 OK):**
```json
{
  "period_days": 30,
  "total_searches": 1234,
  "failed_searches": 23,
  "avg_results_per_query": 8.5,
  "top_queries": [
    {"query": "repack", "count": 234},
    {"query": "download", "count": 189},
    {"query": "installation", "count": 156}
  ],
  "searches_by_day": [
    {"date": "2024-01-01", "count": 45},
    {"date": "2024-01-02", "count": 67}
  ]
}
```

---

### API Keys

#### List API Keys
```http
GET /api/v1/keys
```

**Response (200 OK):**
```json
{
  "keys": [
    {
      "id": 1,
      "name": "Production API",
      "prefix": "ss_abc...",
      "rate_limit_per_minute": 100,
      "requests_count": 5234,
      "last_used_at": "2024-01-15T10:00:00Z",
      "created_at": "2024-01-01T00:00:00Z",
      "expires_at": null,
      "is_active": true
    }
  ]
}
```

---

#### Create API Key
```http
POST /api/v1/keys
```

**Request Body:**
```json
{
  "name": "Development",
  "rate_limit_per_minute": 60,
  "site_id": null,
  "expires_at": "2024-12-31T23:59:59Z"
}
```

**Response (201 Created):**
```json
{
  "id": 2,
  "key": "ss_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "name": "Development",
  "rate_limit_per_minute": 60,
  "created_at": "2024-01-15T12:00:00Z",
  "expires_at": "2024-12-31T23:59:59Z"
}
```

**Important:** The full key is only shown once on creation. Store it securely.

---

#### Revoke API Key
```http
DELETE /api/v1/keys/{key_id}
```

**Response (204 No Content)**

---

### Health & Status

#### Health Check
```http
GET /health
```

No authentication required.

**Response (200 OK):**
```json
{
  "status": "alive",
  "timestamp": "2024-01-15T12:00:00Z"
}
```

---

#### Readiness Check
```http
GET /ready
```

**Response (200 OK):**
```json
{
  "status": "ready",
  "checks": {
    "database": {"healthy": true, "latency_ms": 12},
    "redis": {"healthy": true},
    "meilisearch": {"healthy": true}
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "status": "not_ready",
  "checks": {
    "database": {"healthy": false, "error": "Connection timeout"}
  }
}
```

---

#### Get Metrics
```http
GET /metrics
```

Returns Prometheus-formatted metrics.

---

## Webhooks

### Scrape Completed Webhook

Subscribe to webhook events to receive notifications when scraping completes.

**Configuration:** Set `webhook_url` in site config.

**Payload:**
```json
{
  "event": "scrape.completed",
  "site_id": 1,
  "domain": "fitgirl-repacks.site",
  "status": "completed",
  "pages_found": 658,
  "duration_seconds": 1800,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Retry Policy:**
- Retries 3 times with exponential backoff
- First retry: 1 second
- Second retry: 5 seconds
- Third retry: 25 seconds

**Signature Verification:**
```
X-Webhook-Signature: sha256=<signature>
```

Verify signature using your webhook secret:
```python
import hmac
import hashlib

expected = hmac.new(
    webhook_secret.encode(),
    request_body.encode(),
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(expected, signature):
    raise ValueError("Invalid signature")
```

---

## Error Handling

### Standard Error Format
```json
{
  "error": "Error code or short message",
  "message": "Human-readable description",
  "details": {},
  "request_id": "uuid-for-debugging"
}
```

### Common Errors

#### Rate Limit Exceeded (429)
```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit of 100 requests per minute exceeded",
  "retry_after": 45
}
```

#### Invalid API Key (401)
```json
{
  "error": "unauthorized",
  "message": "Invalid or expired API key"
}
```

#### Validation Error (400)
```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "details": {
    "url": ["Invalid URL format"],
    "max_depth": ["Must be between 1 and 5"]
  }
}
```

#### Site Not Found (404)
```json
{
  "error": "not_found",
  "message": "Site with ID 999 not found"
}
```

#### Scraping Failed (500)
```json
{
  "error": "scraping_failed",
  "message": "Failed to scrape site",
  "details": {
    "error_type": "timeout",
    "url": "https://example.com"
  }
}
```

---

## Pagination

List endpoints support cursor-based pagination:

**Request:**
```http
GET /api/v1/sites?limit=20&offset=40
```

**Response:**
```json
{
  "sites": [...],
  "total": 156,
  "skip": 40,
  "limit": 20,
  "has_more": true,
  "next_offset": 60
}
```

---

## SDK Examples

### Python
```python
import requests

class SiteSearchClient:
    def __init__(self, api_key, base_url="https://api.yourdomain.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
    
    def search(self, query, site_id=None):
        params = {"q": query}
        if site_id:
            params["site_id"] = site_id
        
        response = requests.get(
            f"{self.base_url}/api/v1/search",
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    def create_site(self, url):
        response = requests.post(
            f"{self.base_url}/api/v1/sites",
            headers=self.headers,
            json={"url": url}
        )
        response.raise_for_status()
        return response.json()

# Usage
client = SiteSearchClient("ss_your_api_key")
results = client.search("repack", site_id=1)
```

### JavaScript/Node.js
```javascript
class SiteSearchClient {
  constructor(apiKey, baseUrl = 'https://api.yourdomain.com') {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
  }
  
  async search(query, siteId = null) {
    const params = new URLSearchParams({ q: query });
    if (siteId) params.append('site_id', siteId);
    
    const response = await fetch(
      `${this.baseUrl}/api/v1/search?${params}`,
      {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`
        }
      }
    );
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  }
}

// Usage
const client = new SiteSearchClient('ss_your_api_key');
const results = await client.search('repack', 1);
```

### cURL
```bash
# Search
curl -X GET "https://api.yourdomain.com/api/v1/search?q=repack&site_id=1" \
  -H "Authorization: Bearer ss_your_api_key"

# Create site
curl -X POST "https://api.yourdomain.com/api/v1/sites" \
  -H "Authorization: Bearer ss_your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "crawl": true}'

# Export
curl -X GET "https://api.yourdomain.com/api/v1/sites/1/export?format=csv" \
  -H "Authorization: Bearer ss_your_api_key" \
  -o export.csv
```

---

## Changelog

### v1.0.0 (2024-01-15)
- Initial API release
- Sites CRUD operations
- Search with typo tolerance
- Export functionality
- API key management
- Analytics endpoints

---

## Support

- **Documentation:** https://docs.yourdomain.com
- **Status Page:** https://status.yourdomain.com
- **Email:** support@yourdomain.com
- **Issues:** https://github.com/yourorg/site-search/issues
