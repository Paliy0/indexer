# Production Deployment

## Overview

This guide covers deploying the Site Search Platform to production using Docker Compose (Phase 3-4) and Kubernetes (Phase 5).

---

## Phase 3-4: Docker Compose Deployment

### Prerequisites

- VPS with 4GB+ RAM (Hetzner, DigitalOcean, AWS, etc.)
- Ubuntu 22.04 LTS
- Domain with DNS access
- SSH access

### Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin

# Verify
docker --version
docker compose version
```

### Application Deployment

**1. Clone Repository**

```bash
cd /var/www
git clone https://github.com/yourorg/site-search.git
cd site-search
```

**2. Environment Configuration**

Create `.env.production`:

```bash
# Database
DATABASE_URL=postgresql://sitesearch:${DB_PASSWORD}@postgres:5432/sitesearch
DB_PASSWORD=$(openssl rand -base64 32)

# Redis
REDIS_URL=redis://redis:6379/0

# Meilisearch
MEILISEARCH_HOST=http://meilisearch:7700
MEILISEARCH_API_KEY=$(openssl rand -base64 32)

# App
WEB_PARSER_PATH=/app/web-parser
DEBUG=False
BASE_DOMAIN=yourdomain.com
SECRET_KEY=$(openssl rand -base64 64)

# SSL (for Let's Encrypt)
LETSENCRYPT_EMAIL=admin@yourdomain.com
```

**3. Web Parser Binary**

```bash
# Build or copy binary
cp /path/to/web-parser .
chmod +x web-parser

# Test it works
./web-parser --version
```

**4. SSL Certificates (Let's Encrypt)**

```bash
# Install certbot
sudo apt install certbot

# Obtain wildcard certificate
certbot certonly \
  --manual \
  --preferred-challenges=dns \
  -d *.yourdomain.com \
  -d yourdomain.com \
  --agree-tos \
  -m admin@yourdomain.com

# Copy certificates
sudo mkdir -p /var/www/site-search/ssl
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/chain.pem ssl/

# Set permissions
sudo chown -R ubuntu:ubuntu ssl
chmod 600 ssl/*
```

**5. Nginx Configuration**

Create `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=search:10m rate=30r/s;
    
    upstream app {
        server app:8000;
    }
    
    # HTTP - Redirect to HTTPS
    server {
        listen 80;
        server_name *.yourdomain.com yourdomain.com;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 301 https://$host$request_uri;
        }
    }
    
    # HTTPS
    server {
        listen 443 ssl http2;
        server_name *.yourdomain.com yourdomain.com;
        
        # SSL
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_trusted_certificate /etc/nginx/ssl/chain.pem;
        
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 1d;
        
        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
        
        # Main location
        location / {
            limit_req zone=general burst=20 nodelay;
            
            proxy_pass http://app;
            proxy_http_version 1.1;
            
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket support
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }
        
        # Static files
        location /static/ {
            alias /var/www/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
        
        # Health check (no rate limit)
        location /health {
            proxy_pass http://app;
            access_log off;
        }
    }
}
```

**6. Docker Compose Production**

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile.prod
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - MEILISEARCH_HOST=${MEILISEARCH_HOST}
      - MEILISEARCH_API_KEY=${MEILISEARCH_API_KEY}
      - WEB_PARSER_PATH=/app/web-parser
      - DEBUG=False
      - BASE_DOMAIN=${BASE_DOMAIN}
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - ./web-parser:/app/web-parser:ro
      - ./static:/var/www/static
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      meilisearch:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  worker:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: celery -A app.celery worker --loglevel=info --concurrency=4 -Q celery,scraping
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - MEILISEARCH_HOST=${MEILISEARCH_HOST}
      - MEILISEARCH_API_KEY=${MEILISEARCH_API_KEY}
      - WEB_PARSER_PATH=/app/web-parser
      - DEBUG=False
      - BASE_DOMAIN=${BASE_DOMAIN}
    volumes:
      - ./web-parser:/app/web-parser:ro
    depends_on:
      - postgres
      - redis
      - meilisearch
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure

  beat:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: celery -A app.celery beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    restart: unless-stopped
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    depends_on:
      - postgres
      - redis

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
      - ./static:/var/www/static:ro
      - ./certbot:/var/www/certbot
    depends_on:
      - app

  postgres:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      - POSTGRES_USER=sitesearch
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=sitesearch
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sitesearch"]
      interval: 10s
      timeout: 5s
      retries: 5
    command: >
      postgres
      -c max_connections=200
      -c shared_buffers=256MB
      -c effective_cache_size=768MB
      -c maintenance_work_mem=64MB

  meilisearch:
    image: getmeili/meilisearch:v1.6
    restart: unless-stopped
    environment:
      - MEILI_MASTER_KEY=${MEILISEARCH_API_KEY}
      - MEILI_HTTP_ADDR=0.0.0.0:7700
    volumes:
      - meili_data:/meili_data
    command: meilisearch --http-addr 0.0.0.0:7700

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data

  # Optional: Certbot for auto-renewal
  certbot:
    image: certbot/certbot
    volumes:
      - ./certbot:/etc/letsencrypt
      - ./ssl:/etc/nginx/ssl
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"

volumes:
  postgres_data:
  meili_data:
  redis_data:
```

**7. Production Dockerfile**

Create `Dockerfile.prod`:

```dockerfile
FROM python:3.11-slim

# Security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 appuser

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Change ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run migrations and start
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**8. Deploy**

```bash
# Build and start
docker-compose -f docker-compose.prod.yml up -d --build

# Check logs
docker-compose -f docker-compose.prod.yml logs -f

# Run migrations manually if needed
docker-compose -f docker-compose.prod.yml exec app alembic upgrade head

# Verify
curl https://yourdomain.com/health
curl https://test.yourdomain.com
```

---

## Phase 5: Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (EKS, GKE, AKS, or self-managed)
- kubectl configured
- Helm 3.x installed

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Ingress Controller                │
│                    (NGINX/Traefik)                   │
└──────────────────┬──────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│   App    │  │  Worker  │  │   Beat   │
│  Pods    │  │   Pods   │  │   Pod    │
│  (x3)    │  │  (x2-10) │  │   (x1)   │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     └─────────────┼─────────────┘
                   ▼
    ┌─────────────────────────────────────┐
    │          Services                    │
    │  PostgreSQL  Redis  Meilisearch     │
    └─────────────────────────────────────┘
```

### Deployment Steps

**1. Create Namespace**

```bash
kubectl create namespace site-search
kubectl config set-context --current --namespace=site-search
```

**2. Create Secrets**

```bash
# Generate secrets
export DB_PASSWORD=$(openssl rand -base64 32)
export MEILI_KEY=$(openssl rand -base64 32)
export SECRET_KEY=$(openssl rand -base64 64)

# Create Kubernetes secrets
kubectl create secret generic db-credentials \
  --from-literal=password="$DB_PASSWORD" \
  --from-literal=url="postgresql://sitesearch:${DB_PASSWORD}@postgres:5432/sitesearch"

kubectl create secret generic meili-credentials \
  --from-literal=master-key="$MEILI_KEY"

kubectl create secret generic app-secrets \
  --from-literal=secret-key="$SECRET_KEY"
```

**3. Deploy PostgreSQL**

```bash
# Using Helm
helm repo add bitnami https://charts.bitnami.com/bitnami

helm install postgres bitnami/postgresql \
  --set auth.database=sitesearch \
  --set auth.username=sitesearch \
  --set auth.password="$DB_PASSWORD" \
  --set persistence.size=20Gi \
  --set resources.requests.memory=512Mi \
  --set resources.requests.cpu=250m
```

**4. Deploy Redis**

```bash
helm install redis bitnami/redis \
  --set auth.enabled=false \
  --set persistence.size=5Gi
```

**5. Deploy Meilisearch**

```yaml
# k8s/meilisearch.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: meilisearch
spec:
  serviceName: meilisearch
  replicas: 1
  selector:
    matchLabels:
      app: meilisearch
  template:
    metadata:
      labels:
        app: meilisearch
    spec:
      containers:
      - name: meilisearch
        image: getmeili/meilisearch:v1.6
        ports:
        - containerPort: 7700
        env:
        - name: MEILI_MASTER_KEY
          valueFrom:
            secretKeyRef:
              name: meili-credentials
              key: master-key
        volumeMounts:
        - name: data
          mountPath: /meili_data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: meilisearch
spec:
  selector:
    app: meilisearch
  ports:
  - port: 7700
```

**6. Deploy Application**

Create Helm chart or use manifests:

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/meilisearch.yaml
kubectl apply -f k8s/app-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/ingress.yaml
```

**7. Configure Ingress**

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: site-search
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  tls:
  - hosts:
    - "*.yourdomain.com"
    - "yourdomain.com"
    secretName: wildcard-tls
  rules:
  - host: "yourdomain.com"
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: site-search-app
            port:
              number: 80
  - host: "*.yourdomain.com"
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: site-search-app
            port:
              number: 80
```

**8. Setup Cert-Manager**

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourdomain.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - dns01:
        route53:
          region: us-east-1
          hostedZoneID: YOUR_ZONE_ID
EOF
```

**9. Run Migrations**

```bash
kubectl exec -it deployment/site-search-app -- alembic upgrade head
```

**10. Verify Deployment**

```bash
# Check all pods
kubectl get pods

# Check services
kubectl get svc

# Check ingress
kubectl get ingress

# View logs
kubectl logs -f deployment/site-search-app
kubectl logs -f deployment/site-search-worker

# Test
curl https://yourdomain.com/health
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Application health
curl https://yourdomain.com/health
curl https://yourdomain.com/ready

# Database
kubectl exec -it deployment/postgres -- pg_isready

# Redis
kubectl exec -it deployment/redis -- redis-cli ping

# Meilisearch
curl https://meilisearch.yourdomain.com/health
```

### Logs

```bash
# Docker Compose
docker-compose -f docker-compose.prod.yml logs -f --tail=100

# Kubernetes
kubectl logs -f deployment/site-search-app
kubectl logs -f deployment/site-search-worker --all-containers

# Follow specific container
kubectl logs -f deployment/site-search-worker -c worker
```

### Backups

**Database:**
```bash
# Docker Compose
docker-compose -f docker-compose.prod.yml exec postgres pg_dump -U sitesearch sitesearch > backup.sql

# Kubernetes
kubectl exec -it deployment/postgres -- pg_dump -U sitesearch sitesearch > backup.sql
```

**Meilisearch:**
```bash
# Trigger dump
curl -X POST "https://meilisearch.yourdomain.com/dumps" \
  -H "Authorization: Bearer $MEILI_KEY"

# Copy from container
docker cp site-search-meilisearch-1:/meili_data/dumps ./backups
```

### Updates

**Rolling Update (Kubernetes):**
```bash
# Update image
kubectl set image deployment/site-search-app app=your-registry/app:v1.1.0

# Monitor rollout
kubectl rollout status deployment/site-search-app

# Rollback if needed
kubectl rollout undo deployment/site-search-app
```

**Docker Compose:**
```bash
# Pull and restart
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d

# With zero downtime (using blue-green)
# (Requires additional setup)
```

---

## Security Checklist

- [ ] SSL/TLS enabled (A+ rating on SSL Labs)
- [ ] Non-root containers
- [ ] Secrets in Kubernetes/Docker secrets, not env files
- [ ] Network policies configured
- [ ] Rate limiting enabled
- [ ] Security headers configured
- [ ] WAF enabled (CloudFlare/AWS WAF)
- [ ] Regular security updates
- [ ] Backup encryption
- [ ] Database not exposed publicly

---

## Troubleshooting

### Issue: Pods stuck in Pending

**Solution:**
```bash
# Check events
kubectl describe pod <pod-name>

# Common issues:
# - Insufficient resources: Resize nodes
# - PVC not bound: Check storage class
# - Image pull error: Check registry credentials
```

### Issue: 502 Bad Gateway

**Solution:**
```bash
# Check if app is running
kubectl get pods
kubectl logs deployment/site-search-app

# Check service endpoints
kubectl get endpoints site-search-app

# Test connectivity
kubectl exec -it deployment/site-search-app -- curl localhost:8000/health
```

### Issue: SSL Certificate Issues

**Solution:**
```bash
# Check certificate status
kubectl describe certificate wildcard-tls

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager

# Renew manually
certbot renew --force-renewal
```

---

## Cost Optimization

### Resource Right-Sizing

```yaml
# Monitor actual usage and adjust
resources:
  requests:
    memory: "256Mi"  # Start here
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

### Use Spot Instances (Workers)

```yaml
# Add toleration for spot nodes
nodeSelector:
  node-type: spot
tolerations:
- key: "spot"
  operator: "Equal"
  value: "true"
  effect: "NoSchedule"
```

---

## Production Checklist

Before going live:

- [ ] SSL certificates valid and auto-renewing
- [ ] Health checks passing
- [ ] Database migrations run
- [ ] Backups configured and tested
- [ ] Monitoring alerts configured
- [ ] Rate limiting enabled
- [ ] Security headers in place
- [ ] Error tracking (Sentry) configured
- [ ] CDN configured (CloudFlare)
- [ ] Documentation updated
- [ ] Runbook created for common issues
- [ ] On-call rotation established
