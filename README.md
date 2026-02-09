# Site Search Platform

A hosted service that creates searchable indexes of any website. Built with modern web technologies including FastAPI, PostgreSQL, Meilisearch, and web-parser.

## 🚀 Built with web-parser

This project uses [web-parser](https://github.com/Paliy0/web-parser), an open-source Go library for web scraping. The indexer project serves as a real-world showcase of how to integrate web-parser into a production application.

### How web-parser fits into the architecture

web-parser is the **core scraping engine** that powers the entire indexing process:

1. **Binary Integration**: The Go binary (`web-parser/web-parser`) is called via subprocess from Python
2. **JSON Output**: web-parser outputs structured JSON with page URLs, titles, and content
3. **Configuration Support**: Supports CSS selectors, URL patterns, and custom headers per site
4. **Crawling**: Follows links with configurable depth limits and respect for robots.txt

### Integration Features

- **Async Processing**: Python's `asyncio` manages the subprocess with streaming output
- **Error Handling**: Graceful handling of timeouts, network errors, and malformed responses
- **Progress Tracking**: Real-time updates during scraping via Server-Sent Events
- **Configuration**: Per-site scraping rules passed to web-parser as command-line arguments

### Architecture Role

In the architecture diagram below, web-parser sits at the bottom layer, responsible for fetching and parsing web content which then flows upward through the system for storage, indexing, and search.

## ✨ Features

- **Web Scraping & Indexing**: Scrape any website and create a searchable index
- **Powerful Search**: Full-text search with typo tolerance, ranking, and highlighting
- **Subdomain Routing**: Access indexed sites via wildcard subdomains (e.g., `docs.example.com`)
- **Background Processing**: Async scraping with Celery workers and real-time progress via SSE
- **API First**: RESTful API with API key authentication and rate limiting
- **Export Options**: Export indexed content as JSON, CSV, or Markdown
- **Analytics Dashboard**: Track search queries and site performance
- **Production Ready**: Docker containers, health checks, Prometheus metrics
- **Responsive UI**: Modern web interface with HTMX for dynamic updates
- **Custom Configuration**: Per-site scraping rules with CSS selectors and regex patterns

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   Landing   │  │   Search    │  │   Admin     │     │
│  │    Page     │  │   Results   │  │   Dashboard │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│            │                 │                  │       │
│            └─────────────────┼──────────────────┘       │
│                             │                          │
│                    ┌────────▼────────┐                │
│                    │   FastAPI App   │                │
│                    │   (Port 8000)   │                │
│                    └────────┬────────┘                │
│            ┌────────────────┼─────────────────┐       │
│            │                │                 │       │
│    ┌───────▼──────┐ ┌──────▼──────┐ ┌───────▼──────┐ │
│    │ PostgreSQL   │ │   Redis      │ │ Meilisearch  │ │
│    │ (Port 5432)  │ │ (Port 6379)  │ │ (Port 7700)  │ │
│    └──────────────┘ └──────────────┘ └──────────────┘ │
│            │                 │                 │       │
│            └─────────────────┼─────────────────┘       │
│                             │                          │
│                    ┌────────▼────────┐                │
│                    │   Celery        │                │
│                    │   Workers       │                │
│                    └────────┬────────┘                │
│                             │                          │
│                    ┌────────▼────────┐                │
│                    │   web-parser    │                │
│                    │   (Go binary)   │                │
│                    └─────────────────┘                │
│                             │                          │
│                    ┌────────▼────────┐                │
│                    │   Target        │                │
│                    │   Websites      │                │
│                    └─────────────────┘                │
└─────────────────────────────────────────────────────────┘
```

## 🛠️ Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL 16 (with SQLite fallback)
- **Search Engine**: Meilisearch
- **Task Queue**: Celery with Redis broker
- **Web Scraping**: web-parser Go library
- **Frontend**: Jinja2 templates, HTMX, modern CSS
- **Monitoring**: Prometheus metrics, health checks
- **Containerization**: Docker, Docker Compose
- **API**: RESTful API with OpenAPI/Swagger documentation

## 🚀 Quick Start with Docker Compose

Get started in 3 commands:

```bash
# 1. Clone and setup environment
git clone <repository-url>
cd indexer
cp .env.example .env
# Edit .env if needed (WEB_PARSER_PATH, MEILI_MASTER_KEY, etc.)

# 2. Build and start all services
docker-compose up -d

# 3. Run initial database migrations
docker-compose exec app alembic upgrade head
```

The application will be available at:
- Web Interface: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Meilisearch Dashboard: http://localhost:7700

## 📖 Manual Local Setup

### Prerequisites

- Python 3.12+
- PostgreSQL 14+ (or SQLite for Phase 1 only)
- Redis 7+
- Go 1.22+ (for building web-parser)
- Node.js (optional, for CSS compilation if needed)

### Step-by-Step Guide

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd indexer
   ```

2. **Set up Python virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Set up PostgreSQL database**
   ```bash
   sudo -u postgres psql -c "CREATE USER indexer_user WITH PASSWORD 'indexer_pass';"
   sudo -u postgres psql -c "CREATE DATABASE indexer_db OWNER indexer_user;"
   ```

5. **Build web-parser Go binary**
   ```bash
   cd web-parser
   go build -o web-parser ./cmd/web-parser
   cd ..
   chmod +x web-parser/web-parser
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start Redis and Meilisearch**
   ```bash
   # Redis
   sudo systemctl start redis-server
   
   # Meilisearch (download binary from GitHub releases)
   # Or use the provided script:
   scripts/start-meilisearch.sh
   ```

8. **Start the application**
   ```bash
   # Start FastAPI app
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   
   # In another terminal, start Celery worker
   celery -A app.celery_app worker --loglevel=info
   
   # In another terminal, start Celery beat for scheduled tasks
   celery -A app.celery_app beat --loglevel=info
   ```

## 📚 API Documentation

### Authentication

All API endpoints require an API key. Generate one via the web interface or:

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"name": "my-api-key", "site_id": null}'
```

Include the API key in requests:
- Header: `X-API-Key: your_api_key_here`
- Query parameter: `?api_key=your_api_key_here`

### Key Endpoints

#### Create and Scrape a Site

```bash
curl -X POST http://localhost:8000/api/v1/sites \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "name": "Example Site",
    "description": "Example website for testing"
  }'
```

#### Search Indexed Pages

```bash
curl -X GET "http://localhost:8000/api/v1/search?q=search+query&limit=10" \
  -H "X-API-Key: your_api_key_here"
```

#### Get Site Details

```bash
curl -X GET http://localhost:8000/api/v1/sites/1 \
  -H "X-API-Key: your_api_key_here"
```

#### Export Site Content

```bash
# JSON export
curl -X GET "http://localhost:8000/api/v1/sites/1/export?format=json" \
  -H "X-API-Key: your_api_key_here" \
  -o export.json

# CSV export
curl -X GET "http://localhost:8000/api/v1/sites/1/export?format=csv" \
  -H "X-API-Key: your_api_key_here" \
  -o export.csv

# Markdown export
curl -X GET "http://localhost:8000/api/v1/sites/1/export?format=md" \
  -H "X-API-Key: your_api_key_here" \
  -o export.md
```

#### Get Search Analytics

```bash
curl -X GET "http://localhost:8000/api/v1/analytics?days=30" \
  -H "X-API-Key: your_api_key_here"
```

### OpenAPI Documentation

Interactive API documentation is available at `http://localhost:8000/docs` when the application is running.

## ⚙️ Configuration Reference

| Environment Variable | Default Value | Description |
|---------------------|---------------|-------------|
| `DATABASE_URL` | `sqlite:///./data/sites.db` | Database connection URL |
| `WEB_PARSER_PATH` | `./web-parser/web-parser` | Path to web-parser Go binary |
| `DEBUG` | `True` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server host address |
| `PORT` | `8000` | Server port |
| `MEILISEARCH_HOST` | `http://127.0.0.1:7700` | Meilisearch server URL |
| `MEILI_MASTER_KEY` | `development-master-key-change-me` | Meilisearch master key |
| `MEILI_DB_PATH` | `./data/meili_data` | Meilisearch data directory |
| `MEILI_ENV` | `development` | Meilisearch environment |
| `BASE_DOMAIN` | (empty) | Base domain for subdomain routing |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

## 🧪 Development Guide

### Running Tests

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/test_database.py -v

# Run tests with coverage
pytest --cov=app --cov-report=html

# Run integration tests
pytest tests/test_integration.py -v
```

### Test Categories

- `tests/test_database.py`: Database CRUD operations
- `tests/test_scraper.py`: Web parser integration
- `tests/test_search.py`: Search engine functionality
- `tests/test_models.py`: SQLAlchemy models
- `tests/test_meilisearch.py`: Meilisearch integration
- `tests/test_htmx.py`: HTMX partial responses
- `tests/test_tasks.py`: Celery background tasks
- `tests/test_middleware.py`: Subdomain middleware
- `tests/test_sse.py`: Server-Sent Events
- `tests/test_auth.py`: API key authentication
- `tests/test_rate_limiter.py`: Rate limiting
- `tests/test_api_v1.py`: REST API endpoints
- `tests/test_export.py`: Export functionality
- `tests/test_analytics.py`: Analytics tracking
- `tests/test_integration.py`: End-to-end workflows

### Adding New Features

1. **Create database models** (in `app/models.py`) with Alembic migrations
2. **Implement business logic** in appropriate module (`app/*.py`)
3. **Add API endpoints** in `app/api_v1.py` or `app/main.py`
4. **Write unit tests** in `tests/` directory
5. **Update OpenAPI documentation** with endpoint descriptions
6. **Run tests** and ensure they pass

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function signatures
- Add docstrings for public functions and classes
- Use async/await for I/O operations
- Follow existing patterns in the codebase

## 📁 Project Structure

```
indexer/
├── app/                          # Python application
│   ├── __init__.py              # Package initialization
│   ├── main.py                  # FastAPI application and routes
│   ├── config.py                # Configuration settings
│   ├── models.py               # SQLAlchemy ORM models
│   ├── db.py                   # Database connection and sessions
│   ├── scraper.py              # Web parser wrapper
│   ├── search.py               # Search engine (SQLite fallback)
│   ├── meilisearch_engine.py   # Meilisearch integration
│   ├── celery_app.py           # Celery configuration
│   ├── tasks.py                # Background tasks
│   ├── auth.py                 # API key authentication
│   ├── rate_limiter.py         # Rate limiting implementation
│   ├── api_v1.py               # Versioned REST API
│   ├── export.py               # Export functionality
│   ├── analytics.py            # Search analytics
│   ├── site_config.py          # Site-specific configuration
│   ├── health.py               # Health check endpoints
│   ├── metrics.py              # Prometheus metrics
│   ├── middleware.py           # HTTP middleware
│   └── templates/              # Jinja2 templates
│       ├── base.html           # Base template with CSS
│       ├── index.html          # Landing page
│       ├── search.html         # Search interface
│       ├── status.html         # Scraping status
│       ├── config.html         # Site configuration
│       ├── analytics.html      # Analytics dashboard
│       └── partials/           # HTMX partial templates
│           └── search_results.html
├── web-parser/                  # Go web parser library
│   ├── cmd/web-parser/         # Command-line interface
│   ├── go.mod                  # Go module file
│   └── go.sum                  # Go dependencies
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_database.py
│   ├── test_scraper.py
│   ├── test_search.py
│   ├── test_models.py
│   ├── test_meilisearch.py
│   ├── test_htmx.py
│   ├── test_tasks.py
│   ├── test_middleware.py
│   ├── test_sse.py
│   ├── test_auth.py
│   ├── test_rate_limiter.py
│   ├── test_api_v1.py
│   ├── test_export.py
│   ├── test_analytics.py
│   └── test_integration.py
├── docs/                        # Documentation
│   ├── phases/                 # Phase implementation guides
│   ├── architecture/           # Architecture diagrams
│   ├── api/                    # API specifications
│   └── testing/               # Testing strategy
├── scripts/                    # Utility scripts
│   ├── export_sqlite.py       # SQLite to PostgreSQL migration
│   ├── import_to_postgres.py  # JSON import to PostgreSQL
│   ├── index_meilisearch.py   # Index pages to Meilisearch
│   ├── start-meilisearch.sh   # Start Meilisearch server
│   ├── backup.sh              # Database backup
│   ├── restore.sh             # Database restore
│   └── backup-meilisearch.sh  # Meilisearch backup
├── alembic/                    # Database migrations
│   ├── versions/              # Migration scripts
│   └── env.py                 # Alembic environment
├── nginx/                      # Nginx configuration templates
│   └── nginx.conf             # Reverse proxy configuration
├── data/                       # Data directory
│   ├── sites.db               # SQLite database (Phase 1)
│   └── meili_data/            # Meilisearch data
├── dumps/                      # Meilisearch dumps
├── docker-compose.yml         # Docker Compose configuration
├── docker-compose.override.yml # Development overrides
├── Dockerfile                 # Multi-stage Docker build
├── requirements.txt           # Python dependencies
├── alembic.ini               # Alembic configuration
├── .env.example              # Environment template
└── .gitignore                # Git ignore rules
```

## 🔧 Troubleshooting

### Common Issues

**Web-parser binary not found:**
```bash
# Ensure the binary exists and is executable
ls -la web-parser/web-parser
chmod +x web-parser/web-parser
```

**Database connection errors:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U indexer_user -d indexer_db -h localhost
```

**Meilisearch not responding:**
```bash
# Check Meilisearch is running
curl http://localhost:7700/health

# Check logs
docker-compose logs meilisearch
```

**Celery tasks not executing:**
```bash
# Check Redis is running
redis-cli ping

# Check Celery worker logs
docker-compose logs worker
```

### Logs

- Application logs: `docker-compose logs app`
- Worker logs: `docker-compose logs worker`
- Database logs: `docker-compose logs postgres`
- Search engine logs: `docker-compose logs meilisearch`

## 📈 Monitoring

### Health Checks

- Liveness: `GET /health` - Simple status check
- Readiness: `GET /ready` - Checks all dependencies
- Metrics: `GET /metrics` - Prometheus metrics

### Prometheus Metrics

The application exposes standard Prometheus metrics:
- HTTP request count and duration
- Database connection pool status
- Search query statistics
- Scraping job metrics

### Flower Dashboard

Monitor Celery tasks with Flower:
```bash
celery -A app.celery_app flower --port=5555
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- [web-parser](https://github.com/Paliy0/web-parser) for the core scraping functionality
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [Meilisearch](https://www.meilisearch.com/) for the search engine
- [Celery](https://docs.celeryq.dev/) for background task processing