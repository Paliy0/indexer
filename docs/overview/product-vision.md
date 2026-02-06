# Product Vision

## Vision Statement

Create the world's simplest way to search any website. Users should be able to turn any site into a searchable database just by visiting a URL.

## Problem Statement

Many websites have poor search functionality or none at all:
- Documentation sites with no search
- Blogs with hundreds of posts but no way to find old content
- E-commerce sites with limited filtering
- Forums and communities with terrible search UX

Users currently have to:
1. Use Google with `site:` operator (unreliable, slow)
2. Manually browse categories (time-consuming)
3. Bookmark pages and organize themselves (manual effort)

## Solution

A hosted service that:
1. Accepts any website URL via subdomain routing
2. Automatically crawls and indexes all content
3. Provides instant, typo-tolerant search
4. Requires zero configuration from users

## Target Users

### Primary: Researchers & Power Users
- Developers searching documentation
- Researchers collecting information
- Content curators organizing resources
- Power users who need better search than the original site provides

### Secondary: Site Owners
- Want to add search to their static site
- Don't want to implement their own search
- Need temporary search for events/campaigns

## User Experience Goals

### Zero Configuration
Users should not need to:
- Create accounts (optional)
- Configure crawlers
- Set up databases
- Write code

### Instant Gratification
- Site indexing starts immediately
- First results available within seconds
- Progress shown in real-time
- Search works while indexing continues

### Universal Compatibility
- Works with any public website
- Handles JavaScript-heavy sites
- Respects robots.txt
- Graceful degradation for complex sites

## Competitive Landscape

| Tool | Strengths | Weaknesses | Our Advantage |
|------|-----------|------------|---------------|
| Google Custom Search | Free, familiar | Limited control, ads | Full control, no ads, instant |
| Algolia DocSearch | Fast, beautiful | Requires config, limited to docs | Works with any site, zero config |
| SiteSearch 360 | Easy integration | Paid, requires site ownership | No ownership required |
| Elasticsearch | Powerful | Complex setup, expensive | Fully managed, subdomain routing |
| Swiftype | Good UI | Expensive, complex | Simple, affordable, wildcard domains |

## Unique Value Proposition

**"Turn any website into a searchable database in seconds - just by visiting a URL."**

Key differentiators:
1. **Subdomain routing**: `site.yourdomain.com` instead of complex setup
2. **Zero configuration**: No code, no API keys, no ownership verification
3. **Universal**: Works with any public site
4. **Instant**: Search available within seconds of starting

## Long-term Vision

### Phase 1-5 (MVP)
Basic search functionality for any site

### Future Enhancements
- Browser extension for one-click indexing
- Compare mode (search across multiple sites)
- Saved searches and alerts
- API for programmatic access
- Custom themes and branding
- Mobile apps
- Offline mode/PWA

## Success Criteria

### Technical
- Index any site with <1000 pages in <5 minutes
- Search latency <200ms for 95th percentile
- 99.9% uptime
- Handle 100 concurrent scrapes

### Business
- 1000 indexed sites in first 6 months
- 90% user satisfaction score
- <5% churn rate
- Sustainable hosting costs <$500/month

## Risk Mitigation

### Technical Risks
| Risk | Mitigation |
|------|------------|
| Scraping blocked by sites | Rotate IPs, respect rate limits, user-agent rotation |
| Large sites crash system | Implement pagination, max page limits, streaming |
| Search performance degrades | Meilisearch clustering, caching, CDN |
| Storage costs explode | Automatic cleanup, compression, tiered storage |

### Legal Risks
| Risk | Mitigation |
|------|------------|
| Copyright issues | Respect robots.txt, no caching of full content, DMCA process |
| Terms of service violations | Clear acceptable use policy, ban list for problematic sites |
| Data privacy | No user tracking, anonymized analytics, GDPR compliance |

## Key Decisions

### Architectural Decisions
1. **Use existing web-parser**: Leverage proven Go tool instead of rebuilding
2. **Start with SQLite**: Simpler than PostgreSQL for Phase 1
3. **Meilisearch over Elasticsearch**: Easier to deploy and manage
4. **HTMX over React**: Faster development, smaller bundle, SEO-friendly

### Product Decisions
1. **Subdomain routing**: More intuitive than query parameters
2. **No authentication required**: Lower barrier to entry
3. **Automatic crawling**: No manual sitemap submission
4. **Public by default**: Indexes are publicly searchable

## Timeline

| Phase | Duration | Completion |
|-------|----------|------------|
| Phase 1: Foundation | 2 weeks | Week 2 |
| Phase 2: Search Engine | 2 weeks | Week 4 |
| Phase 3: Wildcard Domains | 2 weeks | Week 6 |
| Phase 4: Advanced Features | 2 weeks | Week 8 |
| Phase 5: Scale | 2 weeks | Week 10 |
| **MVP Complete** | **10 weeks** | **Week 10** |

## Resources

### Team Requirements
- 1 Backend Developer (Python/FastAPI)
- 1 Frontend Developer (HTMX/JavaScript)
- 1 DevOps Engineer (Docker/K8s)
- 1 QA/Testing

### Infrastructure
- Phase 1-2: Single VPS ($20/month)
- Phase 3-4: Docker Compose on VPS ($50/month)
- Phase 5: Kubernetes cluster ($200-500/month)

### External Services
- Domain registration: $12/year
- SSL certificates: Free (Let's Encrypt)
- Monitoring: Free tier (Datadog/New Relic)
- Error tracking: Free tier (Sentry)

## Conclusion

This platform fills a gap in the market for simple, instant website search. By leveraging existing tools and focusing on zero-configuration user experience, we can deliver value quickly while building toward a scalable, feature-rich product.
