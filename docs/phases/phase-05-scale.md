# Phase 5: Scale & Reliability

## Goal
**"Production ready"** - Handle multiple sites, monitor health, scale horizontally.

## Duration
2 weeks

## Success Criteria
- [ ] Docker Compose → Kubernetes migration
- [ ] Horizontal scaling of workers
- [ ] Rate limiting & abuse prevention
- [ ] Monitoring (Prometheus + Grafana)
- [ ] Backup strategy
- [ ] Handle 10 concurrent scrapes
- [ ] 99.9% uptime

## User Stories (This Phase)
- **Story 5.1**: Rate Limiting (already in Phase 4, enhanced here)
- **Story 5.2**: Monitoring Dashboard
- **Story 5.3**: Auto-scaling
- **Story 5.4**: Backup and Recovery

## What's New in Phase 5

### Infrastructure Evolution
| Component | Phase 4 | Phase 5 |
|-----------|---------|---------|
| Orchestration | Docker Compose | Kubernetes |
| Scaling | Manual | Horizontal Pod Autoscaling |
| Monitoring | Basic logs | Prometheus + Grafana |
| Backups | None | Automated daily backups |
| CDN | None | CloudFlare/AWS CloudFront |
| Database | Single instance | Primary + replicas |

### New Services
```yaml
# Kubernetes additions
services:
  - prometheus      # Metrics collection
  - grafana         # Visualization
  - alertmanager    # Alert routing
  - jaeger          # Distributed tracing
  - cert-manager    # Automatic SSL in K8s
  - external-dns    # DNS management
```

## Technical Components

### 1. Kubernetes Architecture

**Namespace Structure:**
```yaml
# namespaces.yml
apiVersion: v1
kind: Namespace
metadata:
  name: site-search
  labels:
    app: site-search
    env: production
---
apiVersion: v1
kind: Namespace
metadata:
  name: site-search-monitoring
  labels:
    app: monitoring
```

**Application Deployment:**
```yaml
# k8s/app-deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: site-search-app
  namespace: site-search
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: site-search
      component: app
  template:
    metadata:
      labels:
        app: site-search
        component: app
    spec:
      containers:
      - name: app
        image: your-registry/site-search-app:latest
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: redis-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: site-search-app
  namespace: site-search
spec:
  selector:
    app: site-search
    component: app
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

**Worker Deployment with HPA:**
```yaml
# k8s/worker-deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: site-search-worker
  namespace: site-search
spec:
  replicas: 2
  selector:
    matchLabels:
      app: site-search
      component: worker
  template:
    metadata:
      labels:
        app: site-search
        component: worker
    spec:
      containers:
      - name: worker
        image: your-registry/site-search-app:latest
        command: ["celery", "-A", "app.celery", "worker", "--loglevel=info", "--concurrency=4"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: site-search-worker-hpa
  namespace: site-search
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: site-search-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: External
    external:
      metric:
        name: celery_queue_length
        selector:
          matchLabels:
            queue: scraping
      target:
        type: AverageValue
        averageValue: "5"  # Scale up when >5 tasks per worker
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
```

**Ingress with Cert-Manager:**
```yaml
# k8s/ingress.yml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: site-search-ingress
  namespace: site-search
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  tls:
  - hosts:
    - "*.yourdomain.com"
    - "yourdomain.com"
    secretName: wildcard-tls
  rules:
  - host: yourdomain.com
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

### 2. Monitoring Stack

**Prometheus Configuration:**
```yaml
# monitoring/prometheus-config.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'site-search-app'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - site-search
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: site-search
      - source_labels: [__meta_kubernetes_pod_label_component]
        action: keep
        regex: app
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        target_label: __address__
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2

  - job_name: 'celery-workers'
    static_configs:
      - targets: ['celery-exporter:5555']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

**Application Metrics:**
```python
# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info
import time
from functools import wraps

# Request metrics
request_count = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Business metrics
search_queries = Counter(
    'search_queries_total',
    'Total search queries',
    ['site_id', 'has_results']
)

scrape_jobs = Counter(
    'scrape_jobs_total',
    'Total scrape jobs',
    ['status']  # started, completed, failed
)

scrape_duration = Histogram(
    'scrape_duration_seconds',
    'Time to complete scrape',
    buckets=[60, 300, 600, 1800, 3600]
)

active_scrapes = Gauge(
    'active_scrapes',
    'Number of scrapes currently running'
)

# Database metrics
db_connections = Gauge(
    'db_connections_active',
    'Active database connections'
)

# Custom decorator
def track_request(endpoint):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                response = await func(*args, **kwargs)
                status = response.status_code
            except Exception as e:
                status = 500
                raise
            finally:
                duration = time.time() - start
                request_count.labels(
                    method=kwargs.get('request').method,
                    endpoint=endpoint,
                    status=status
                ).inc()
                request_duration.labels(
                    method=kwargs.get('request').method,
                    endpoint=endpoint
                ).observe(duration)
            return response
        return wrapper
    return decorator
```

**Grafana Dashboard:**
```json
{
  "dashboard": {
    "title": "Site Search Platform",
    "panels": [
      {
        "title": "Request Rate",
        "type": "stat",
        "targets": [{
          "expr": "rate(http_requests_total[5m])"
        }]
      },
      {
        "title": "Response Time (p95)",
        "type": "graph",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
        }]
      },
      {
        "title": "Error Rate",
        "type": "stat",
        "targets": [{
          "expr": "rate(http_requests_total{status=~'5..'}[5m])"
        }]
      },
      {
        "title": "Active Scrapes",
        "type": "stat",
        "targets": [{
          "expr": "active_scrapes"
        }]
      },
      {
        "title": "Scrape Duration",
        "type": "graph",
        "targets": [{
          "expr": "rate(scrape_duration_seconds_sum[5m]) / rate(scrape_duration_seconds_count[5m])"
        }]
      },
      {
        "title": "Queue Length",
        "type": "stat",
        "targets": [{
          "expr": "celery_queue_length{queue='scraping'}"
        }]
      },
      {
        "title": "Database Connections",
        "type": "graph",
        "targets": [{
          "expr": "db_connections_active"
        }]
      },
      {
        "title": "Pod Status",
        "type": "table",
        "targets": [{
          "expr": "kube_pod_status_phase{namespace='site-search'}"
        }]
      }
    ]
  }
}
```

**Alerting Rules:**
```yaml
# monitoring/alert-rules.yml
groups:
- name: site-search
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} errors per second"

  - alert: SlowScrapes
    expr: scrape_duration_seconds > 3600
    for: 1m
    labels:
      severity: warning
    annotations:
      summary: "Scrape taking too long"
      description: "Scrape has been running for over 1 hour"

  - alert: QueueBacklog
    expr: celery_queue_length > 20
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Celery queue backlog"
      description: "Queue has {{ $value }} pending tasks"

  - alert: DatabaseConnectionsHigh
    expr: db_connections_active > 80
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High database connection count"

  - alert: PodCrashLooping
    expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Pod crash looping"
      description: "Pod {{ $labels.pod }} is restarting frequently"

  - alert: DiskSpaceLow
    expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Low disk space"
      description: "Disk is {{ $value }}% full"
```

### 3. Backup Strategy

**Database Backups:**
```yaml
# k8s/backup-cronjob.yml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: site-search
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15-alpine
            command:
            - /bin/sh
            - -c
            - |
              pg_dump $DATABASE_URL | gzip > /backups/postgres-$(date +%Y%m%d-%H%M%S).sql.gz
              # Keep only last 30 days
              find /backups -name "postgres-*.sql.gz" -mtime +30 -delete
            env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
            volumeMounts:
            - name: backups
              mountPath: /backups
          volumes:
          - name: backups
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
---
# Offsite backup to S3
apiVersion: batch/v1
kind: CronJob
metadata:
  name: s3-backup
  namespace: site-search
spec:
  schedule: "0 3 * * *"  # Daily at 3 AM (after local backup)
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: s3-backup
            image: amazon/aws-cli:latest
            command:
            - /bin/sh
            - -c
            - |
              aws s3 sync /backups s3://site-search-backups/postgres/ --delete
            env:
            - name: AWS_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: aws-credentials
                  key: access-key
            - name: AWS_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: aws-credentials
                  key: secret-key
            volumeMounts:
            - name: backups
              mountPath: /backups
          volumes:
          - name: backups
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

**Meilisearch Backups:**
```yaml
# k8s/meilisearch-backup.yml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: meilisearch-backup
  namespace: site-search
spec:
  schedule: "0 1 * * *"  # Daily at 1 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: getmeili/meilisearch:v1.6
            command:
            - /bin/sh
            - -c
            - |
              # Create dump
              curl -X POST "http://meilisearch:7700/dumps" \
                -H "Authorization: Bearer $MEILI_MASTER_KEY"
              
              # Wait for dump to complete
              sleep 60
              
              # Copy to backups
              cp /meili_data/dumps/*.dump /backups/meilisearch-$(date +%Y%m%d).dump
              
              # Cleanup old dumps
              find /backups -name "meilisearch-*.dump" -mtime +7 -delete
            env:
            - name: MEILI_MASTER_KEY
              valueFrom:
                secretKeyRef:
                  name: meili-credentials
                  key: master-key
            volumeMounts:
            - name: meili-data
              mountPath: /meili_data
            - name: backups
              mountPath: /backups
          volumes:
          - name: meili-data
            persistentVolumeClaim:
              claimName: meilisearch-pvc
          - name: backups
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
```

**Backup Restoration Procedure:**
```bash
#!/bin/bash
# scripts/restore-backup.sh

set -e

BACKUP_FILE=$1
DB_URL=$2

echo "Restoring from $BACKUP_FILE..."

# Drop and recreate database
echo "Dropping existing database..."
dropdb site-search || true
createdb site-search

# Restore from backup
echo "Restoring backup..."
gunzip -c "$BACKUP_FILE" | psql "$DB_URL"

echo "Restore complete!"

# Verify
psql "$DB_URL" -c "SELECT COUNT(*) FROM sites;"
```

### 4. Health Checks & Probes

**Comprehensive Health Endpoint:**
```python
# app/health.py
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
import redis
import meilisearch

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Liveness probe - basic check that app is running.
    
    Returns 200 if app is alive.
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}

@router.get("/ready")
async def readiness_check():
    """
    Readiness probe - check all dependencies are available.
    
    Returns 200 if app can serve traffic.
    """
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "meilisearch": await check_meilisearch(),
    }
    
    all_healthy = all(c["healthy"] for c in checks.values())
    
    if all_healthy:
        return {
            "status": "ready",
            "checks": checks
        }
    else:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks}
        )

async def check_database():
    """Check database connectivity."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT 1"))
            await result.scalar()
        return {"healthy": True, "latency_ms": latency}
    except Exception as e:
        return {"healthy": False, "error": str(e)}

async def check_redis():
    """Check Redis connectivity."""
    try:
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        return {"healthy": True}
    except Exception as e:
        return {"healthy": False, "error": str(e)}

async def check_meilisearch():
    """Check Meilisearch connectivity."""
    try:
        client = meilisearch.Client(settings.meilisearch_host)
        client.health()
        return {"healthy": True}
    except Exception as e:
        return {"healthy": False, "error": str(e)}

@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

### 5. Disaster Recovery Plan

**Recovery Time Objectives (RTO):**
- Service: 15 minutes
- Database: 30 minutes
- Full system: 2 hours

**Recovery Point Objectives (RPO):**
- Database: 24 hours (daily backups)
- Meilisearch: 24 hours
- User data: 0 (real-time replication if enabled)

**Recovery Procedures:**

1. **Service Failure:**
```bash
# Kubernetes will auto-restart
kubectl rollout restart deployment/site-search-app -n site-search

# Check status
kubectl get pods -n site-search
kubectl logs -f deployment/site-search-app -n site-search
```

2. **Database Corruption:**
```bash
# Stop workers
kubectl scale deployment site-search-worker --replicas=0 -n site-search

# Restore from backup
./scripts/restore-backup.sh /backups/postgres-20240115-020000.sql.gz $DATABASE_URL

# Restart workers
kubectl scale deployment site-search-worker --replicas=2 -n site-search

# Re-index Meilisearch
kubectl exec -it deployment/site-search-app -n site-search -- python -c "from app.tasks import reindex_all; reindex_all.delay()"
```

3. **Complete Cluster Failure:**
```bash
# Provision new cluster
terraform apply

# Restore from S3
aws s3 sync s3://site-search-backups/postgres/ ./backups/

# Run restoration
./scripts/restore-backup.sh ./backups/latest.sql.gz $DATABASE_URL

# Redeploy applications
kubectl apply -f k8s/
```

## Testing Criteria

### Load Testing
- [ ] Handle 1000 concurrent users
- [ ] Handle 100 concurrent scrapes
- [ ] Search latency <200ms at 1000 req/s
- [ ] Auto-scaling triggers within 60 seconds
- [ ] Zero-downtime deployments

### Failure Testing
- [ ] Pod failure → traffic routed to healthy pods
- [ ] Database failover → <30s downtime
- [ ] Redis failure → graceful degradation
- [ ] Meilisearch restart → automatic reconnection
- [ ] Network partition → proper handling

### Backup Testing
- [ ] Daily backup completes successfully
- [ ] Backup restoration works in staging
- [ ] Meilisearch dump/restore verified
- [ ] Point-in-time recovery tested
- [ ] Offsite backup (S3) confirmed

### Monitoring Tests
- [ ] All alerts fire correctly
- [ ] Dashboard shows accurate data
- [ ] PagerDuty/Opsgenie integration works
- [ ] On-call rotation documented

## Deployment

### Helm Chart
```yaml
# helm/site-search/Chart.yaml
apiVersion: v2
name: site-search
description: Site Search Platform
type: application
version: 1.0.0
appVersion: "1.0.0"
dependencies:
  - name: postgresql
    version: 12.x.x
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: 17.x.x
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
```

### Deployment Command
```bash
# Deploy to production
helm upgrade --install site-search ./helm/site-search \
  --namespace site-search \
  --values values-production.yaml \
  --set image.tag=v1.0.0

# Verify deployment
kubectl get pods -n site-search
kubectl get ingress -n site-search
kubectl get hpa -n site-search
```

## Success Metrics

- **Uptime**: 99.9% measured over 30 days
- **RTO**: <15 minutes for service recovery
- **RPO**: <24 hours data loss
- **Latency**: p95 <200ms for search
- **Scaling**: 0-10 workers in <2 minutes
- **MTTR**: <30 minutes mean time to recovery
- **MTBF**: >720 hours mean time between failures

## Cost Optimization

**Resource Efficiency:**
- Use spot instances for workers (70% savings)
- Right-size pods based on metrics
- Archive old backups to Glacier ($0.004/GB vs $0.023/GB)
- Use reserved instances for database (40% savings)

**Estimated Monthly Costs (AWS):**
- EKS cluster: $73
- EC2 (3x t3.medium): $90
- RDS PostgreSQL: $100
- ElastiCache Redis: $30
- S3 storage: $10
- CloudWatch: $20
- Data transfer: $20
- **Total: ~$363/month**

## Documentation Deliverables

- [ ] Kubernetes manifests
- [ ] Helm charts
- [ ] Monitoring dashboards (Grafana JSON)
- [ ] Alert rules
- [ ] Runbooks for common issues
- [ ] Disaster recovery procedures
- [ ] Cost analysis
- [ ] Security hardening guide
- [ ] Performance tuning guide

## Definition of Done

Phase 5 is complete when:
1. Kubernetes cluster running in production
2. Horizontal pod autoscaling working
3. Prometheus + Grafana monitoring active
4. Alerts configured and tested
5. Daily backups running
6. Disaster recovery tested
7. Documentation complete
8. 99.9% uptime achieved for 7 days
9. Load testing passed
10. Security audit passed
