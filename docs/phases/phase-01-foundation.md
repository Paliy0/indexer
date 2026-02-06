# Phase 1: Foundation MVP

## Goal
**"First working search"** - Users can scrape one site and search its content via web UI.

## Duration
2 weeks

## Success Criteria
- [ ] Scrape target site using web-parser subprocess
- [ ] Store results in SQLite
- [ ] Basic full-text search working
- [ ] Simple HTML search interface
- [ ] Deploy to single VPS

## User Stories (This Phase)
- **Story 1.1**: Basic Site Scraping
- **Story 1.2**: Simple Search  
- **Story 1.3**: View Search Results
- **Story 1.4**: Scrape Status

## Technical Components

### 1. Backend (FastAPI)

**Endpoints Required:**
```python
# Core endpoints to implement
POST /api/scrape              # Trigger scrape job
GET  /api/search?q=query      # Search indexed pages
GET  /api/status              # Check if site is indexed
GET  /api/sites/{id}          # Get site details
```

**Directory Structure:**
```
app/
├── __init__.py
├── main.py              # FastAPI application entry
├── config.py            # Configuration settings
├── database.py          # SQLite connection & models
├── scraper.py           # Web parser integration
├── search.py            # Search logic
└── templates/           # Jinja2 templates
    ├── base.html
    ├── index.html
    ├── search.html
    └── status.html
```

### 2. Database (SQLite)

**Schema:**
```sql
-- sites table
CREATE TABLE sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    domain TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, scraping, completed, failed
    page_count INTEGER DEFAULT 0,
    last_scraped TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- pages table
CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (site_id) REFERENCES sites(id)
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE pages_fts USING fts5(
    title,
    content,
    content='pages',
    content_rowid='id'
);
```

**Indexes:**
```sql
CREATE INDEX idx_pages_site_id ON pages(site_id);
CREATE INDEX idx_sites_domain ON sites(domain);
CREATE INDEX idx_sites_status ON sites(status);
```

### 3. Web Parser Integration

**Implementation Strategy:**
```python
# app/scraper.py
import subprocess
import json
from pathlib import Path

class WebParser:
    """Wrapper around the web-parser Go binary."""
    
    def __init__(self, binary_path: str = "./web-parser"):
        self.binary_path = Path(binary_path)
        if not self.binary_path.exists():
            raise FileNotFoundError(f"web-parser not found at {binary_path}")
    
    def scrape(self, url: str, crawl: bool = True) -> list[dict]:
        """
        Scrape a website and return list of pages.
        
        Args:
            url: Target URL to scrape
            crawl: Whether to crawl related pages
            
        Returns:
            List of page dicts: {'url': str, 'title': str, 'content': str}
        """
        cmd = [
            str(self.binary_path),
            "-url", url,
            "-format", "json",
            "-o", "-"  # Output to stdout
        ]
        
        if crawl:
            cmd.extend(["-crawl", "-max-depth", "2"])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            raise ScrapingError(f"Scraping failed: {result.stderr}")
        
        data = json.loads(result.stdout)
        return data.get("pages", [])
```

**Binary Placement:**
- Place `web-parser` binary in project root
- Ensure it's executable: `chmod +x web-parser`
- Add to `.gitignore` (binary shouldn't be in repo)

### 4. Search Implementation (SQLite FTS5)

**Full-Text Search Setup:**
```python
# app/search.py
import sqlite3
from typing import List, Dict

class SearchEngine:
    """SQLite FTS5 search implementation."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def search(self, query: str, site_id: int = None, limit: int = 20) -> List[Dict]:
        """
        Search pages using FTS5.
        
        Args:
            query: Search query string
            site_id: Optional site ID to filter by
            limit: Maximum results to return
            
        Returns:
            List of matching pages with relevance scores
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                p.id,
                p.url,
                p.title,
                snippet(pages_fts, 2, '<mark>', '</mark>', '...', 30) as snippet,
                rank
            FROM pages_fts
            JOIN pages p ON pages_fts.rowid = p.id
            WHERE pages_fts MATCH ?
        """
        params = [query]
        
        if site_id:
            sql += " AND p.site_id = ?"
            params.append(site_id)
        
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "url": row[1],
                "title": row[2],
                "snippet": row[3],
                "rank": row[4]
            }
            for row in results
        ]
```

### 5. Frontend (Jinja2 Templates)

**Page Structure:**

`templates/base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Site Search{% endblock %}</title>
    <style>
        /* Minimal CSS for Phase 1 */
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .search-box { width: 100%; padding: 10px; font-size: 16px; margin: 20px 0; }
        .result { margin: 20px 0; padding: 15px; border: 1px solid #ddd; }
        .result h3 { margin-top: 0; }
        .result .url { color: #666; font-size: 14px; }
        .result .snippet { margin-top: 10px; }
        mark { background: yellow; }
    </style>
</head>
<body>
    {% block content %}{% endblock %}
</body>
</html>
```

`templates/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Site Search Platform</h1>

<form action="/api/scrape" method="POST">
    <label for="url">Enter website URL:</label>
    <input type="url" id="url" name="url" placeholder="https://example.com" required>
    <button type="submit">Start Scraping</button>
</form>

<h2>Recently Indexed Sites</h2>
{% if sites %}
    <ul>
    {% for site in sites %}
        <li>
            <a href="/site/{{ site.domain }}">{{ site.url }}</a>
            - {{ site.status }} ({{ site.page_count }} pages)
        </li>
    {% endfor %}
    </ul>
{% else %}
    <p>No sites indexed yet.</p>
{% endif %}
{% endblock %}
```

`templates/search.html`:
```html
{% extends "base.html" %}
{% block title %}Search {{ site.domain }}{% endblock %}
{% block content %}
<h1>Search {{ site.domain }}</h1>

<form action="/site/{{ site.domain }}/search" method="GET">
    <input type="search" name="q" value="{{ query }}" placeholder="Search..." class="search-box">
    <button type="submit">Search</button>
</form>

{% if results %}
    <p>Found {{ results|length }} results</p>
    
    {% for result in results %}
    <div class="result">
        <h3><a href="{{ result.url }}" target="_blank">{{ result.title }}</a></h3>
        <div class="url">{{ result.url }}</div>
        <div class="snippet">{{ result.snippet|safe }}</div>
    </div>
    {% endfor %}
{% elif query %}
    <p>No results found for "{{ query }}"</p>
{% endif %}
{% endblock %}
```

### 6. Configuration

**Environment Variables:**
```bash
# .env file
DATABASE_URL=sqlite:///./data/sites.db
WEB_PARSER_PATH=./web-parser
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

**Config Module:**
```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/sites.db"
    web_parser_path: str = "./web-parser"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
```

## API Endpoints Specification

### POST /api/scrape
**Description**: Start scraping a website

**Request Body:**
```json
{
  "url": "https://fitgirl-repacks.site",
  "crawl": true,
  "max_depth": 2
}
```

**Response (202 Accepted):**
```json
{
  "site_id": 1,
  "url": "https://fitgirl-repacks.site",
  "status": "scraping",
  "message": "Scraping started"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Invalid URL format"
}
```

### GET /api/sites/{site_id}
**Description**: Get site details and status

**Response (200 OK):**
```json
{
  "id": 1,
  "url": "https://fitgirl-repacks.site",
  "domain": "fitgirl-repacks.site",
  "status": "completed",
  "page_count": 234,
  "last_scraped": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-15T10:25:00Z"
}
```

### GET /api/search
**Description**: Search indexed pages

**Query Parameters:**
- `q` (required): Search query
- `site_id` (optional): Filter by site ID
- `limit` (optional): Results per page (default: 20, max: 100)

**Response (200 OK):**
```json
{
  "query": "repack",
  "total_results": 45,
  "results": [
    {
      "id": 123,
      "url": "https://fitgirl-repacks.site/game-title/",
      "title": "Game Title Repack",
      "snippet": "This is a <mark>repack</mark> of the game...",
      "rank": 0.85
    }
  ]
}
```

## Development Workflow

### Prerequisites
- Python 3.11+
- web-parser binary (Go)
- SQLite3

### Setup Commands
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastapi uvicorn jinja2 python-multipart aiofiles

# Create data directory
mkdir -p data

# Run migrations (create tables)
python -c "from app.database import init_db; init_db()"

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing Commands
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Test specific module
pytest tests/test_scraper.py -v
```

## Deployment

### VPS Setup (Ubuntu 22.04)

```bash
# Install Python
sudo apt update
sudo apt install python3-pip python3-venv sqlite3

# Create app directory
mkdir -p /var/www/site-search
cd /var/www/site-search

# Clone/copy code
git clone <repo> .

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy web-parser binary
cp /path/to/web-parser .
chmod +x web-parser

# Create systemd service
sudo nano /etc/systemd/system/site-search.service
```

**systemd service file:**
```ini
[Unit]
Description=Site Search Platform
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/var/www/site-search
Environment="DATABASE_URL=sqlite:///./data/sites.db"
Environment="WEB_PARSER_PATH=/var/www/site-search/web-parser"
ExecStart=/var/www/site-search/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Start service
sudo systemctl daemon-reload
sudo systemctl enable site-search
sudo systemctl start site-search

# Check status
sudo systemctl status site-search
```

## Testing Criteria

### Functional Tests
- [ ] Submit URL via web form → Returns site_id
- [ ] Check status endpoint → Shows "scraping" then "completed"
- [ ] Search endpoint returns results with highlighted terms
- [ ] Results link to original URLs
- [ ] Page count matches scraped pages

### Performance Tests
- [ ] Search query returns in < 1 second
- [ ] Can handle 5 concurrent scrapes
- [ ] Database remains responsive during scraping
- [ ] UI loads in < 2 seconds

### Edge Cases
- [ ] Invalid URL returns proper error
- [ ] Duplicate URL handled gracefully
- [ ] Empty search query handled
- [ ] Large pages (>1MB) don't crash system
- [ ] Network timeouts handled gracefully

## Success Metrics

- **Scraping**: Successfully scrape 5 test sites without errors
- **Search**: Return relevant results for common queries
- **Performance**: Page load < 3 seconds, search < 1 second
- **Stability**: No crashes during 24-hour test period

## Known Limitations (Phase 1)

1. **Synchronous scraping**: Blocks during long scrapes
2. **Single server**: No horizontal scaling
3. **Basic search**: No typo tolerance, no ranking
4. **No progress tracking**: Users wait without feedback
5. **SQLite limits**: Not suitable for high concurrency
6. **No subdomain routing**: All sites on same domain

## Handoff to Phase 2

Phase 2 will address:
- Async scraping with progress tracking
- PostgreSQL migration
- Meilisearch integration for fuzzy search
- Modern UI with HTMX
- Better error handling

## Deliverables

- [ ] FastAPI application with core endpoints
- [ ] SQLite database with FTS5 search
- [ ] Web parser integration
- [ ] Basic HTML templates
- [ ] Deployment scripts
- [ ] Unit tests (80%+ coverage)
- [ ] Integration tests for scrape → search flow
- [ ] Documentation (this file)

## Definition of Done

Phase 1 is complete when:
1. A user can submit a URL via web form
2. The site is scraped using web-parser
3. Data is stored in SQLite
4. User can search and get relevant results
5. Application is deployed and accessible
6. All tests pass
7. Documentation is complete
