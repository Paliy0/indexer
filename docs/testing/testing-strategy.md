# Testing Strategy

## Overview

Comprehensive testing approach covering unit, integration, E2E, performance, and load testing.

## Testing Pyramid

```
       /\
      /  \     E2E Tests (Few)
     /____\    (Critical user journeys)
    /      \
   /        \   Integration Tests (Some)
  /__________\  (API, Database, Services)
 /            \
/______________\ Unit Tests (Many)
                (Functions, Components)
```

---

## Test Categories

### 1. Unit Tests

**Scope:** Individual functions and classes
**Tools:** pytest, pytest-asyncio
**Coverage Target:** 80%+

**Example Test:**
```python
# tests/test_scraper.py
import pytest
from app.scraper import WebParser

@pytest.fixture
def scraper():
    return WebParser(binary_path="./web-parser")

@pytest.mark.asyncio
async def test_scrape_single_page(scraper):
    """Test scraping a single page."""
    pages = await scraper.scrape("https://example.com", crawl=False)
    
    assert len(pages) == 1
    assert pages[0]["url"] == "https://example.com"
    assert "title" in pages[0]
    assert "content" in pages[0]

@pytest.mark.asyncio
async def test_scrape_invalid_url(scraper):
    """Test handling invalid URL."""
    with pytest.raises(ScrapingError) as exc_info:
        await scraper.scrape("not-a-valid-url")
    
    assert "Invalid URL" in str(exc_info.value)

@pytest.mark.asyncio
async def test_scrape_timeout(scraper):
    """Test timeout handling."""
    with pytest.raises(ScrapingError):
        await scraper.scrape("https://slow-site.com", timeout=1)
```

**Configuration:**
```ini
# pytest.ini
[pytest]
testpaths = tests
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning
addopts = 
    -v
    --tb=short
    --strict-markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    e2e: marks tests as end-to-end tests
```

### 2. Integration Tests

**Scope:** API endpoints, database, external services
**Tools:** pytest, httpx, TestClient
**Database:** Separate test database

**Example:**
```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.models import Site

@pytest.fixture
def client(db_session):
    """Create test client with database override."""
    def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)

@pytest.fixture
def sample_site(db_session):
    """Create a sample site for testing."""
    site = Site(
        url="https://test-site.com",
        domain="test-site.com",
        status="completed",
        page_count=10
    )
    db_session.add(site)
    db_session.commit()
    return site

def test_create_site(client):
    """Test creating a new site via API."""
    response = client.post(
        "/api/v1/sites",
        json={"url": "https://example.com", "crawl": True}
    )
    
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "scraping"
    assert "site_id" in data

def test_search_site(client, sample_site):
    """Test searching a site."""
    response = client.get(
        "/api/v1/search",
        params={"q": "test", "site_id": sample_site.id}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert "total_hits" in data

@pytest.mark.integration
def test_full_scrape_flow(client, db_session):
    """Test complete scrape → index → search flow."""
    # 1. Create site
    response = client.post("/api/v1/sites", json={"url": "https://httpbin.org/html"})
    assert response.status_code == 202
    site_id = response.json()["site_id"]
    
    # 2. Wait for scraping (in real test, mock or wait)
    import time
    time.sleep(5)  # Or use Celery test mode
    
    # 3. Check status
    response = client.get(f"/api/v1/sites/{site_id}")
    assert response.json()["status"] == "completed"
    
    # 4. Search
    response = client.get("/api/v1/search", params={"q": "test", "site_id": site_id})
    assert response.status_code == 200
```

### 3. E2E Tests

**Scope:** Full user workflows
**Tools:** Playwright, pytest-playwright
**Environment:** Staging or ephemeral environment

**Example:**
```python
# tests/e2e/test_search_flow.py
import pytest
from playwright.async_api import Page, expect

@pytest.mark.e2e
async def test_user_search_journey(page: Page, base_url: str):
    """Test complete user search journey."""
    
    # 1. Visit site
    await page.goto(f"{base_url}")
    
    # 2. Enter URL to index
    await page.fill("input[name='url']", "https://example.com")
    await page.click("button[type='submit']")
    
    # 3. Wait for indexing
    await expect(page.locator(".status")).to_contain_text("scraping")
    
    # Wait up to 2 minutes for indexing
    await page.wait_for_selector("text=Indexing Complete", timeout=120000)
    
    # 4. Search
    await page.fill("input[name='q']", "test query")
    await page.press("input[name='q']", "Enter")
    
    # 5. Verify results
    await expect(page.locator(".result-item")).to_have_count.greater_than(0)
    
    # 6. Click result
    await page.click(".result-item a")
    
    # 7. Verify new tab opened
    new_page = await page.wait_for_event("popup")
    assert "example.com" in new_page.url

@pytest.mark.e2e
async def test_subdomain_routing(page: Page, base_url: str):
    """Test subdomain-based site access."""
    
    # Visit subdomain
    await page.goto("https://test-site.localhost:8000")
    
    # Should show either:
    # - Search page (if indexed)
    # - Setup page (if not indexed)
    
    title = await page.title()
    assert "test-site" in title.lower() or "setup" in title.lower()
```

**Configuration:**
```json
// playwright.config.json
{
  "testDir": "tests/e2e",
  "use": {
    "baseURL": "http://localhost:8000",
    "headless": true,
    "screenshot": "only-on-failure",
    "video": "retain-on-failure"
  },
  "projects": [
    {
      "name": "chromium",
      "use": { "browserName": "chromium" }
    },
    {
      "name": "firefox",
      "use": { "browserName": "firefox" }
    }
  ]
}
```

### 4. Performance Tests

**Scope:** Response times, throughput
**Tools:** Locust, k6, Apache Bench
**Targets:**
- Search: p95 < 200ms
- API: p95 < 100ms
- Page load: < 2s

**Locust Example:**
```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class SiteSearchUser(HttpUser):
    wait_time = between(1, 5)
    
    def on_start(self):
        """Setup - get API key or create session."""
        self.client.headers = {
            "Authorization": "Bearer ss_test_key"
        }
    
    @task(10)
    def search(self):
        """Simulate search."""
        self.client.get("/api/v1/search?q=repack&limit=20")
    
    @task(5)
    def search_with_filters(self):
        """Search with filters."""
        self.client.get("/api/v1/search?q=game&site_id=1&limit=20")
    
    @task(3)
    def get_site_info(self):
        """Get site details."""
        self.client.get("/api/v1/sites/1")
    
    @task(1)
    def create_site(self):
        """Create new site (lower frequency)."""
        self.client.post(
            "/api/v1/sites",
            json={"url": "https://example.com"}
        )
```

**Running:**
```bash
# Run Locust
locust -f tests/performance/locustfile.py --host=https://yourdomain.com

# Or k6
k6 run tests/performance/search-load.js
```

**k6 Example:**
```javascript
// tests/performance/search-load.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // Ramp up
    { duration: '5m', target: 100 },  // Steady state
    { duration: '2m', target: 200 },  // Ramp up
    { duration: '5m', target: 200 },  // Peak load
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'],  // 95% under 200ms
    http_req_failed: ['rate<0.01'],     // <1% errors
  },
};

export default function () {
  const res = http.get('https://yourdomain.com/api/v1/search?q=test&limit=20', {
    headers: {
      'Authorization': 'Bearer ss_test_key',
    },
  });
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 200ms': (r) => r.timings.duration < 200,
  });
  
  sleep(1);
}
```

### 5. Load Tests

**Scope:** System behavior under extreme load
**Tools:** Locust, k6, Gatling
**Targets:**
- 1000 concurrent users
- 100 concurrent scrapes
- 99.9% uptime

**Load Test Scenarios:**

1. **Gradual Ramp:**
   - Start: 10 users
   - Ramp: +50 users every 30s
   - Peak: 1000 users
   - Duration: 30 minutes

2. **Spike Test:**
   - Normal: 100 users
   - Spike: 2000 users for 5 minutes
   - Recovery: Back to 100

3. **Soak Test:**
   - Load: 500 users
   - Duration: 24 hours
   - Monitor: Memory leaks, connection pool exhaustion

### 6. Security Tests

**Scope:** Vulnerability scanning, penetration testing
**Tools:** OWASP ZAP, Burp Suite, SonarQube

**Security Checklist:**
- [ ] SQL injection (use parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] CSRF protection
- [ ] Authentication bypass
- [ ] Authorization checks
- [ ] Rate limiting effectiveness
- [ ] Sensitive data exposure
- [ ] Security headers

**OWASP ZAP Baseline Scan:**
```bash
# Run ZAP baseline scan
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://yourdomain.com \
  -g gen.conf \
  -r zap-report.html
```

### 7. Contract Tests

**Scope:** API contract validation
**Tools:** Pact, schemathesis

**Example:**
```python
# tests/contract/test_api_contract.py
import schemathesis
from app.main import app

schema = schemathesis.from_asgi("/openapi.json", app)

@schema.parametrize()
def test_api_contract(case):
    """Test all API endpoints against OpenAPI schema."""
    case.call_and_validate()
```

---

## Test Data Management

### Fixtures

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Site, Page

# Test database
TEST_DATABASE_URL = "postgresql://test:test@localhost:5432/test_db"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def sample_site_data():
    return {
        "url": "https://test-site.com",
        "domain": "test-site.com",
        "status": "completed",
        "page_count": 100
    }

@pytest.fixture
def sample_pages_data():
    return [
        {
            "url": "https://test-site.com/page-1",
            "title": "Page 1",
            "content": "Content for page 1"
        },
        {
            "url": "https://test-site.com/page-2",
            "title": "Page 2",
            "content": "Content for page 2"
        }
    ]
```

### Factories

```python
# tests/factories.py
import factory
from app.models import Site, Page

class SiteFactory(factory.Factory):
    class Meta:
        model = Site
    
    url = factory.Sequence(lambda n: f"https://test-site-{n}.com")
    domain = factory.Sequence(lambda n: f"test-site-{n}.com")
    status = "completed"
    page_count = 10

class PageFactory(factory.Factory):
    class Meta:
        model = Page
    
    url = factory.Sequence(lambda n: f"https://test-site.com/page-{n}")
    title = factory.Sequence(lambda n: f"Page {n}")
    content = factory.Faker("paragraph", nb_sentences=5)
    site = factory.SubFactory(SiteFactory)
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7
        ports:
          - 6379:6379
      
      meilisearch:
        image: getmeili/meilisearch:v1.6
        ports:
          - 7700:7700
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run linting
      run: |
        flake8 app/
        black --check app/
    
    - name: Run unit tests
      run: pytest tests/unit -v --cov=app --cov-report=xml
      env:
        DATABASE_URL: postgresql://postgres:test@localhost:5432/test_db
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Start services
      run: docker-compose -f docker-compose.test.yml up -d
    
    - name: Run integration tests
      run: pytest tests/integration -v -m integration
    
    - name: Cleanup
      run: docker-compose -f docker-compose.test.yml down

  e2e-tests:
    runs-on: ubuntu-latest
    needs: integration-tests
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Install Playwright
      run: |
        pip install pytest-playwright
        playwright install
    
    - name: Start application
      run: |
        docker-compose -f docker-compose.test.yml up -d
        sleep 30  # Wait for services
    
    - name: Run E2E tests
      run: pytest tests/e2e -v -m e2e
    
    - name: Upload screenshots
      if: failure()
      uses: actions/upload-artifact@v3
      with:
        name: screenshots
        path: test-results/

  performance-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Run k6 tests
      uses: grafana/k6-action@v0.3.1
      with:
        filename: tests/performance/search-load.js
```

---

## Test Environments

### Local Development
- SQLite or PostgreSQL
- Mock external services
- Fast feedback (< 10s)

### CI/CD
- PostgreSQL in Docker
- Full service stack
- Parallel test execution

### Staging
- Production-like environment
- Real external services
- Data anonymization

### Production (Canary)
- Minimal testing
- Smoke tests only
- Monitor metrics

---

## Test Coverage

### Coverage Targets

| Component | Target | Current |
|-----------|--------|---------|
| Models | 90% | - |
| API endpoints | 85% | - |
| Services | 80% | - |
| Utilities | 75% | - |
| Overall | 80% | - |

### Exclusions
```ini
# .coveragerc
[run]
source = app
omit = 
    */tests/*
    */venv/*
    */migrations/*
    app/main.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

---

## Best Practices

### 1. Test Isolation
- Use database transactions
- Mock external APIs
- Clean up test data

### 2. Deterministic Tests
- Fixed random seeds
- Frozen timestamps
- Mocked time

### 3. Fast Tests
- Parallel execution
- In-memory databases
- Minimal I/O

### 4. Readable Tests
- Clear test names
- Given/When/Then structure
- Helper functions

### Example Pattern:**
```python
def test_search_returns_matching_pages():
    """Given indexed pages, when searching, then return matches."""
    # Given
    site = create_site_with_pages([
        {"title": "Python Tutorial", "content": "Learn Python"},
        {"title": "Java Guide", "content": "Learn Java"}
    ])
    
    # When
    results = search(query="python", site_id=site.id)
    
    # Then
    assert len(results) == 1
    assert results[0].title == "Python Tutorial"
```

---

## Reporting

### Test Reports

```bash
# Generate HTML report
pytest --html=report.html --self-contained-html

# Generate JUnit XML
pytest --junitxml=report.xml

# Coverage report
pytest --cov=app --cov-report=html --cov-report=xml
```

### Dashboards
- GitHub Actions artifacts
- Codecov integration
- Test result trends
- Performance graphs

---

## Troubleshooting

### Common Issues

**Flaky Tests:**
- Add retry logic
- Use explicit waits
- Mock time-sensitive code

**Slow Tests:**
- Profile test execution
- Use test markers to categorize
- Parallelize with pytest-xdist

**Database Deadlocks:**
- Use proper transaction isolation
- Avoid shared state
- Use connection pooling

---

## Continuous Improvement

### Metrics to Track
- Test execution time
- Coverage trends
- Flaky test rate
- Bug escape rate
- Test maintenance cost

### Review Process
- Weekly test review
- Refactor old tests
- Update test strategy
- Share testing knowledge
