# Site Search Platform

A hosted service that creates searchable indexes of any website, accessible via custom subdomains.

## Quick Start

```
https://fitgirl-repacks.yourdomain.com  → Searchable index of fitgirl-repacks.site
https://docs.python.yourdomain.com      → Searchable index of docs.python.org
```

## Project Overview

This platform allows users to:
1. Enter any website URL via subdomain (e.g., `site-name.yourdomain.com`)
2. Automatically scrape and index the entire site
3. Search through all pages with full-text search
4. Filter and browse results efficiently

## Documentation Structure

```
docs/
├── overview/           # Project overview and vision
│   ├── README.md       # This file
│   ├── product-vision.md
│   └── user-stories.md
├── phases/             # Phase-by-phase development guides
│   ├── phase-01-foundation.md
│   ├── phase-02-search-engine.md
│   ├── phase-03-wildcard-domains.md
│   ├── phase-04-advanced-features.md
│   └── phase-05-scale.md
├── api/                # API specifications
│   ├── api-reference.md
│   └── webhooks.md
├── architecture/       # System architecture
│   ├── system-overview.md
│   ├── data-flow.md
│   └── tech-stack.md
├── deployment/         # Deployment guides
│   ├── local-development.md
│   ├── staging-setup.md
│   └── production-deployment.md
└── testing/            # Testing documentation
    ├── testing-strategy.md
    ├── test-cases.md
    └── load-testing.md
```

## Development Phases

The project is organized into 5 phases, each building on the previous:

| Phase | Name | Duration | Goal | Status |
|-------|------|----------|------|--------|
| 1 | Foundation | 2 weeks | First working search | Planned |
| 2 | Search Engine | 2 weeks | Production-grade search | Planned |
| 3 | Wildcard Domains | 2 weeks | True subdomain routing | Planned |
| 4 | Advanced Features | 2 weeks | Power user features | Planned |
| 5 | Scale | 2 weeks | Production ready | Planned |

## Core Technologies

- **Backend**: Python 3.11+ with FastAPI
- **Database**: SQLite (Phase 1) → PostgreSQL (Phase 2+)
- **Search**: Meilisearch
- **Queue**: Redis + Celery (Phase 3+)
- **Scraper**: Go web-parser (existing tool)
- **Frontend**: HTMX + Jinja2 templates
- **Hosting**: VPS → Docker → Kubernetes

## Getting Started for Developers

1. Read the [Product Vision](overview/product-vision.md)
2. Review [Phase 1 documentation](phases/phase-01-foundation.md)
3. Check [Local Development Setup](deployment/local-development.md)
4. Review [API Specifications](api/api-reference.md)

## Success Metrics

- **Phase 1**: Successfully scrape and search 5 test sites
- **Phase 2**: Search results in <200ms, typo-tolerant search
- **Phase 3**: Wildcard domains working, background jobs functional
- **Phase 4**: API usage, exports working, analytics dashboard
- **Phase 5**: Handle 10+ concurrent scrapes, 99.9% uptime

## Contributing

Each phase has specific deliverables and testing criteria. See individual phase documents for details.

## License

[To be determined]
