# User Stories

## Personas

### Persona 1: Alex - The Developer
- **Role**: Full-stack developer
- **Goal**: Search documentation sites efficiently
- **Pain Point**: Many docs have poor search (e.g., old WordPress sites, GitHub wikis)
- **Tech Savvy**: High
- **Usage**: Daily

### Persona 2: Sarah - The Researcher
- **Role**: Academic researcher
- **Goal**: Find specific information across multiple sites
- **Pain Point**: Information scattered across poorly searchable sites
- **Tech Savvy**: Medium
- **Usage**: Weekly

### Persona 3: Mike - The Content Curator
- **Role**: Marketing manager
- **Goal**: Monitor competitor content and industry trends
- **Pain Point**: Need to search competitor blogs and news sites
- **Tech Savvy**: Medium
- **Usage**: Weekly

### Persona 4: Lisa - The Site Owner
- **Role**: Small business owner
- **Goal**: Add search to her static website
- **Pain Point**: Static site (Jekyll/Hugo) with no search
- **Tech Savvy**: Low-Medium
- **Usage**: Set up once, minimal ongoing use

---

## User Stories by Phase

### Phase 1: Foundation MVP

**Story 1.1**: Basic Site Scraping
```
As Alex (developer)
I want to enter a website URL
So that the system starts scraping it immediately

Acceptance Criteria:
- I can submit a URL via web form
- System shows "Scraping in progress" status
- I can see number of pages found
- Scraping completes and shows "Ready for search"
```

**Story 1.2**: Simple Search
```
As Alex
I want to search through scraped pages
So that I can find specific content

Acceptance Criteria:
- Search box is available after scraping completes
- Entering a query returns matching pages
- Results show page title and snippet
- Results are ordered by relevance
```

**Story 1.3**: View Search Results
```
As Alex
I want to see search results in a list
So that I can choose which page to visit

Acceptance Criteria:
- Each result shows: title, URL, snippet
- Clicking result opens original page in new tab
- Results are paginated (10 per page)
```

**Story 1.4**: Scrape Status
```
As Sarah (researcher)
I want to see scraping progress
So that I know when I can start searching

Acceptance Criteria:
- Progress bar shows % complete
- Shows current page being scraped
- Shows total pages found so far
- Error message if scraping fails
```

---

### Phase 2: Search Engine & UI

**Story 2.1**: Typo-Tolerant Search
```
As Sarah
I want search to handle my typos
So that I still find what I'm looking for

Acceptance Criteria:
- Searching "instalation" finds "installation"
- Searching "pythn" finds "python"
- No results shows "Did you mean..." suggestions
```

**Story 2.2**: Search Highlighting
```
As Alex
II want to see where my search terms appear
So that I can quickly assess relevance

Acceptance Criteria:
- Search terms are highlighted in results
- Highlighting works for partial matches
- Multiple terms are all highlighted
```

**Story 2.3**: Real-time Search
```
As Sarah
I want search results to update as I type
So that I can refine my query quickly

Acceptance Criteria:
- Results update 300ms after I stop typing
- No page reload required
- Shows "Searching..." indicator
```

**Story 2.4**: Filter by Date
```
As Mike (curator)
I want to filter results by date
So that I can find recent content

Acceptance Criteria:
- Filter by: Today, This Week, This Month, This Year, All Time
- Filter shows count of results for each option
- Multiple filters can be combined
```

**Story 2.5**: Mobile-Friendly UI
```
As Sarah
I want to use the search on my phone
So that I can research anywhere

Acceptance Criteria:
- UI works on screens down to 320px
- Touch-friendly buttons and inputs
- No horizontal scrolling
- Fast loading on mobile networks
```

---

### Phase 3: Wildcard Domains & Workers

**Story 3.1**: Subdomain Access
```
As Alex
I want to access my indexed site via subdomain
So that the URL is clean and memorable

Acceptance Criteria:
- Visiting `site-name.yourdomain.com` loads the search
- Subdomain is extracted from URL automatically
- SSL certificate covers wildcard subdomains
- HTTP redirects to HTTPS automatically
```

**Story 3.2**: Background Scraping
```
As Mike
I want scraping to happen in the background
So that I can close the tab and come back later

Acceptance Criteria:
- Can close browser while scraping continues
- Revisiting subdomain shows current status
- Email notification when complete (optional)
```

**Story 3.3**: Multiple Concurrent Scrapes
```
As Sarah
I want to scrape multiple sites simultaneously
So that I can compare results across sites

Acceptance Criteria:
- Can submit multiple sites without waiting
- Each site gets its own subdomain
- Progress tracked independently for each site
```

**Story 3.4**: Re-index Site
```
As Mike
I want to refresh the index periodically
So that new content is searchable

Acceptance Criteria:
- "Re-index" button available on search page
- Shows last indexed date
- New scrape replaces old index
- Option to schedule automatic re-indexing
```

---

### Phase 4: Advanced Features

**Story 4.1**: Custom CSS Selectors
```
As Alex
I want to specify which parts of pages to index
So that I exclude navigation and ads

Acceptance Criteria:
- Can specify CSS selector (e.g., `.content`, `#main`)
- Preview shows what content will be indexed
- Advanced settings available but hidden by default
```

**Story 4.2**: REST API
```
As Alex
I want programmatic access to search
So that I can integrate with my tools

Acceptance Criteria:
- API key generation available
- REST endpoints documented
- Rate limits clearly communicated
- JSON responses
```

**Story 4.3**: Export Results
```
As Sarah
I want to export search results
So that I can use them in my research

Acceptance Criteria:
- Export formats: JSON, CSV, Markdown
- Export all results or just current page
- Download starts immediately
```

**Story 4.4**: Search Analytics
```
As Lisa (site owner)
I want to see what people search for
So that I can improve my content

Acceptance Criteria:
- Dashboard shows popular queries
- Shows failed searches (no results)
- Shows most clicked results
- Data exportable
```

**Story 4.5**: API Access
```
As Alex
I want to create API keys
So that I can automate searches

Acceptance Criteria:
- API key generation interface
- Keys can be revoked
- Usage statistics shown
- Clear documentation provided
```

---

### Phase 5: Scale & Reliability

**Story 5.1**: Rate Limiting
```
As a platform owner
I want to prevent abuse
So that service remains available for all

Acceptance Criteria:
- Rate limits: 100 requests/minute per IP
- Clear error messages when limit hit
- Contact form to request limit increase
- Premium tier with higher limits (future)
```

**Story 5.2**: Monitoring Dashboard
```
As a platform owner
I want to monitor system health
So that I can respond to issues quickly

Acceptance Criteria:
- Dashboard shows: active scrapes, queue depth, error rate
- Alerts for: high error rates, disk space, memory
- Historical metrics visible
- Mobile-friendly dashboard
```

**Story 5.3**: Auto-scaling
```
As a platform owner
I want workers to scale automatically
So that I don't manually add capacity

Acceptance Criteria:
- Workers increase when queue depth > 10
- Workers decrease when idle > 10 minutes
- Scaling events logged
- Costs monitored
```

**Story 5.4**: Backup and Recovery
```
As a platform owner
I want automated backups
So that data is never lost

Acceptance Criteria:
- Daily backups of database
- Weekly backups of search index
- 30-day retention
- Tested recovery procedure documented
```

---

## Technical Stories

### Phase 1
**T1.1**: SQLite Database Setup
```
As a developer
I want a simple database schema
So that I can store scraped data

Acceptance Criteria:
- SQLite database created automatically
- Tables: sites, pages, queries
- Connection pooling configured
- Migration system in place
```

**T1.2**: Web Parser Integration
```
As a developer
I want to call web-parser from Python
So that I can reuse existing code

Acceptance Criteria:
- Subprocess wrapper around web-parser binary
- JSON output parsed correctly
- Errors handled gracefully
- Timeout configured (30s default)
```

### Phase 2
**T2.1**: Meilisearch Integration
```
As a developer
I want to index pages in Meilisearch
So that search is fast and fuzzy

Acceptance Criteria:
- Documents indexed with proper schema
- Typo tolerance configured
- Highlighting enabled
- Relevancy tuned
```

**T2.2**: PostgreSQL Migration
```
As a developer
I want to migrate from SQLite to PostgreSQL
So that I can handle concurrent requests

Acceptance Criteria:
- Data migration script created
- Connection pooling with asyncpg
- Environment-based configuration
- Zero-downtime migration possible
```

### Phase 3
**T3.1**: Redis Queue Setup
```
As a developer
I want a job queue for background tasks
So that scraping doesn't block the API

Acceptance Criteria:
- Redis configured as broker
- Celery workers running
- Tasks have retry logic
- Dead letter queue for failures
```

**T3.2**: Wildcard SSL
```
As a developer
I want wildcard SSL certificates
So that subdomains are secure

Acceptance Criteria:
- Let's Encrypt wildcard cert obtained
- Auto-renewal configured
- Nginx configured for subdomains
- HTTPS redirects work
```

### Phase 4
**T4.1**: API Authentication
```
As a developer
I want API key authentication
So that I can control access

Acceptance Criteria:
- JWT or API key based auth
- Rate limiting per key
- Key rotation support
- Usage tracking
```

### Phase 5
**T5.1**: Kubernetes Deployment
```
As a DevOps engineer
I want Kubernetes manifests
So that I can deploy to k8s

Acceptance Criteria:
- Helm charts created
- Auto-scaling configured
- Health checks implemented
- Rolling updates supported
```

---

## Story Prioritization

### Must Have (MVP)
- Story 1.1: Basic Site Scraping
- Story 1.2: Simple Search
- Story 1.3: View Search Results
- Story 2.1: Typo-Tolerant Search
- Story 3.1: Subdomain Access

### Should Have (Phase 2-3)
- Story 1.4: Scrape Status
- Story 2.2: Search Highlighting
- Story 2.3: Real-time Search
- Story 2.5: Mobile-Friendly UI
- Story 3.2: Background Scraping

### Could Have (Phase 4-5)
- Story 2.4: Filter by Date
- Story 3.3: Multiple Concurrent Scrapes
- Story 3.4: Re-index Site
- Story 4.1: Custom CSS Selectors
- Story 4.2: REST API
- Story 4.3: Export Results

### Won't Have (Future)
- Story 4.4: Search Analytics
- Story 4.5: API Access
- Story 5.1: Rate Limiting (basic only)
- Story 5.2: Monitoring Dashboard
- Story 5.3: Auto-scaling
- Story 5.4: Backup and Recovery
