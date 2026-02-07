# Multi-stage Dockerfile for Site Search Platform
# Stage 1: Build web-parser Go binary
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Copy web-parser source
COPY web-parser/ ./

# Build the web-parser binary (using cmd/web-parser as the main package)
RUN go build -o web-parser ./cmd/web-parser

# Stage 2: Runtime environment
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Copy web-parser binary from builder stage
COPY --from=builder /build/web-parser /app/web-parser/web-parser
RUN chmod +x /app/web-parser/web-parser

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose application port
EXPOSE 8000

# Default command - run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
