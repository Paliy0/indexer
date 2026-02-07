# Local Development Setup

## Prerequisites

- Python 3.11+
- Go 1.21+ (for building web-parser)
- SQLite3 (Phase 1) or Docker (Phase 2+)
- Git

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/yourorg/site-search.git
cd site-search
```

### 2. Build Web Parser (Go Tool)

The indexer uses [web-parser](https://github.com/Paliy0/web-parser), an open-source Go library for web scraping. Build the CLI binary:

```bash
cd web-parser
go build -o web-parser ./cmd/web-parser
cd ..

# Verify the binary works
./web-parser/web-parser -h
```

### 3. Python Environment Setup

```bash
# Create virtual environment
python -m venv venv

# Activate
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 4. Configuration

Create `.env` file:

```bash
# Phase 1: Basic setup
DATABASE_URL=sqlite:///./data/sites.db
WEB_PARSER_PATH=./web-parser
DEBUG=True
HOST=0.0.0.0
PORT=8000
```

For Phase 2+ (using Docker):

```bash
# Phase 2+ with Docker services
DATABASE_URL=postgresql://user:pass@localhost:5432/sitesearch
REDIS_URL=redis://localhost:6379/0
MEILISEARCH_HOST=http://localhost:7700
WEB_PARSER_PATH=./web-parser
DEBUG=True
BASE_DOMAIN=localhost
```

### 5. Database Setup

**Phase 1 (SQLite):**
```bash
# Create data directory
mkdir -p data

# Initialize database (automatic on first run)
python -c "from app.database import init_db; init_db()"
```

**Phase 2+ (PostgreSQL with Docker):**
```bash
# Start services
docker-compose up -d postgres meilisearch redis

# Run migrations
alembic upgrade head

# Create initial data (optional)
python scripts/seed_data.py
```

### 6. Run Application

```bash
# Development server with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or with custom config
python -m app.main
```

Access application at: http://localhost:8000

---

## Phase-by-Phase Development

### Phase 1: Foundation

```bash
# Requirements
cat requirements-phase1.txt
# fastapi
# uvicorn
# jinja2
# python-multipart
# aiosqlite
# pytest
# pytest-asyncio

# Start developing
git checkout phase-1
uvicorn app.main:app --reload
```

### Phase 2: Search Engine

```bash
# Start infrastructure
docker-compose up -d postgres meilisearch

# Install Phase 2 dependencies
pip install -r requirements-phase2.txt

# Run migrations
alembic upgrade head

# Index test data
python scripts/index_test_data.py

# Start app
uvicorn app.main:app --reload
```

### Phase 3: Workers

```bash
# Start all services
docker-compose up -d

# Terminal 1: Start API
uvicorn app.main:app --reload

# Terminal 2: Start Celery worker
celery -A app.celery worker --loglevel=info

# Terminal 3: Start Celery beat (optional)
celery -A app.celery beat --loglevel=info
```

### Phase 4: Advanced Features

```bash
# All services running
# Just start the app
uvicorn app.main:app --reload
```

---

## Development Tools

### Code Quality

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Format code
black app/

# Lint
flake8 app/
pylint app/

# Type check
mypy app/

# Run all checks
make lint
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test
pytest tests/test_scraper.py -v

# Watch mode
ptw  # pytest-watch
```

### Debugging

```bash
# With pdb
python -m pdb -m uvicorn app.main:app

# With VS Code
# Add launch.json configuration
```

**launch.json:**
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload"],
      "jinja": true
    }
  ]
}
```

---

## Project Structure

```
site-search/
├── app/                      # Main application
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration
│   ├── database.py          # Database setup
│   ├── models.py            # SQLAlchemy models
│   ├── scraper.py           # Web parser integration
│   ├── search.py            # Search engine
│   ├── celery.py            # Celery configuration
│   ├── tasks.py             # Background tasks
│   ├── auth.py              # Authentication
│   ├── middleware.py        # Custom middleware
│   ├── templates/           # Jinja2 templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── search.html
│   │   └── partials/
│   └── static/              # Static files
│       ├── css/
│       └── js/
├── alembic/                 # Database migrations
│   ├── versions/
│   └── env.py
├── tests/                   # Test files
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_scraper.py
│   └── test_search.py
├── scripts/                 # Utility scripts
│   ├── seed_data.py
│   ├── export_data.py
│   └── backup.sh
├── web-parser/              # Go scraper (submodule or separate)
│   ├── main.go
│   └── web-parser (binary)
├── docs/                    # Documentation
├── requirements.txt         # Dependencies
├── requirements-dev.txt     # Dev dependencies
├── docker-compose.yml       # Docker services
├── Dockerfile               # App container
├── .env                     # Environment variables (not in git)
├── .env.example             # Example env file
├── .gitignore
└── README.md
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | Database connection string |
| `REDIS_URL` | Phase 3+ | - | Redis connection string |
| `MEILISEARCH_HOST` | Phase 2+ | - | Meilisearch URL |
| `MEILISEARCH_API_KEY` | Phase 2+ | - | Meilisearch API key |
| `WEB_PARSER_PATH` | Yes | `./web-parser` | Path to Go binary |
| `DEBUG` | No | `False` | Enable debug mode |
| `HOST` | No | `0.0.0.0` | Server bind host |
| `PORT` | No | `8000` | Server port |
| `BASE_DOMAIN` | Phase 3+ | - | Domain for subdomains |
| `SECRET_KEY` | Phase 4+ | - | For JWT/API key signing |

---

## Common Issues

### Issue: Web-parser binary not found

**Solution:**
```bash
# Build the binary (web-parser is now a library with CLI in cmd/web-parser)
cd web-parser && go build -o web-parser ./cmd/web-parser
cd ..
./web-parser/web-parser -h
```

### Issue: Database locked (SQLite)

**Solution:**
```python
# In config, reduce pool size
# SQLite doesn't handle concurrent writes well
# Or switch to PostgreSQL for Phase 2+
```

### Issue: Meilisearch connection refused

**Solution:**
```bash
# Start Meilisearch
docker-compose up -d meilisearch

# Verify it's running
curl http://localhost:7700/health
```

### Issue: Celery tasks not executing

**Solution:**
```bash
# Check Redis is running
docker-compose ps redis

# Check worker is running
celery -A app.celery inspect active

# View logs
celery -A app.celery worker --loglevel=debug
```

---

## IDE Configuration

### VS Code

**Extensions:**
- Python
- Pylance
- Docker
- Thunder Client (API testing)

**Settings:**
```json
{
  "python.defaultInterpreterPath": "./venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true
}
```

### PyCharm

1. Set Python interpreter to venv
2. Enable Django support (for templates)
3. Configure run configuration for uvicorn

---

## Useful Commands

```bash
# Database
alembic revision --autogenerate -m "Description"
alembic upgrade head
alembic downgrade -1

# Docker
docker-compose up -d
docker-compose logs -f app
docker-compose down
docker-compose down -v  # Remove volumes

# Celery
celery -A app.celery worker --loglevel=info
celery -A app.celery beat --loglevel=info
celery -A app.celery flower --port=5555  # Monitoring UI

# Testing
pytest
pytest -x  # Stop on first failure
pytest --lf  # Run last failed tests
pytest -s  # Show print statements

# Maintenance
python scripts/cleanup.py
python scripts/backup.py
```

---

## Next Steps

After local development:
1. Test with staging environment
2. Deploy to production
3. Monitor and optimize

See [Staging Setup](staging-setup.md) and [Production Deployment](production-deployment.md)
