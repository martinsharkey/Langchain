# Operations Guide

Comprehensive guide for operating, monitoring, and maintaining StrategyOps v2.0 in production.

---

## Table of Contents

1. [Deployment Architecture](#deployment-architecture)
2. [Service Management](#service-management)
3. [Monitoring and Alerting](#monitoring-and-alerting)
4. [Logging and Troubleshooting](#logging-and-troubleshooting)
5. [Backup and Recovery](#backup-and-recovery)
6. [Performance Tuning](#performance-tuning)
7. [Security Operations](#security-operations)

---

## Deployment Architecture

### Production Environment

**Infrastructure Stack**:
- **Container Orchestration**: Docker Compose (staging) / Kubernetes (production)
- **Load Balancing**: Nginx / AWS ALB
- **Database**: PostgreSQL (primary), Redis (cache)
- **Monitoring**: Prometheus, Grafana, Jaeger
- **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **Message Queue**: Redis or RabbitMQ

### Environment Configurations

**development/.env**:
```ini
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
DATABASE_URL=postgresql://localhost/strategyops_dev
REDIS_URL=redis://localhost:6379/0
```

**staging/.env**:
```ini
ENVIRONMENT=staging
DEBUG=false
LOG_LEVEL=INFO
DATABASE_URL=postgresql://db-staging.example.com/strategyops_staging
REDIS_URL=redis://redis-staging.example.com:6379/0
```

**production/.env**:
```ini
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
DATABASE_URL=postgresql://db-prod.example.com/strategyops
REDIS_URL=redis://redis-prod.example.com:6379/0
API_KEY_REQUIRED=true
```

---

## Service Management

### Starting Services

**Docker Compose (Development/Staging)**:
```bash
# Start all services
docker compose -f docker-compose.yml -f docker-compose-prod.yml up -d

# Start specific service
docker compose up -d discovery-service

# Start with specific environment
docker compose --env-file=.env.production up -d
```

**Kubernetes (Production)**:
```bash
# Apply configuration
kubectl apply -f k8s/

# Deploy specific service
kubectl apply -f k8s/discovery-service-deployment.yaml

# Check status
kubectl get pods -n strategyops
kubectl get services -n strategyops
```

### Monitoring Service Status

```bash
# Docker Compose
docker compose ps
docker compose status

# Kubernetes
kubectl get pods -n strategyops -o wide
kubectl describe pod <pod-name> -n strategyops
kubectl logs <pod-name> -n strategyops --tail=100 -f
```

### Restarting Services

**Single Service**:
```bash
# Docker Compose
docker compose restart discovery-service

# Kubernetes
kubectl rollout restart deployment discovery-service -n strategyops
```

**All Services**:
```bash
# Docker Compose
docker compose restart

# Kubernetes
kubectl rollout restart deployment -n strategyops
```

### Rolling Updates

```bash
# Docker Compose
docker compose pull
docker compose up -d --no-deps --build

# Kubernetes
kubectl set image deployment/discovery-service discovery-service=myregistry/discovery:v2 -n strategyops
kubectl rollout status deployment/discovery-service -n strategyops
```

### Rolling Back

```bash
# Kubernetes - Rollback to previous version
kubectl rollout undo deployment/discovery-service -n strategyops

# Verify rollback
kubectl rollout history deployment/discovery-service -n strategyops
```

---

## Monitoring and Alerting

### Health Checks

**Service Health Endpoint**:
```bash
# Check single service
curl -s http://localhost:8001/health | jq .

# Expected response
{
  "status": "healthy",
  "service": "discovery-service",
  "version": "2.0.0",
  "uptime_seconds": 3600,
  "checks": {
    "database": "ok",
    "redis": "ok",
    "disk_space": "ok"
  }
}
```

**Script to check all services**:
```bash
#!/bin/bash
services=(8001 8002 8003 8004 8005 8006)
for port in "${services[@]}"; do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health)
  echo "Port $port: $status"
done
```

### Prometheus Monitoring

**Prometheus Configuration** (`prometheus.yml`):
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'discovery-service'
    static_configs:
      - targets: ['localhost:8001']
    metrics_path: '/metrics'

  - job_name: 'optimization-service'
    static_configs:
      - targets: ['localhost:8002']

  # ... other services
  
  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:5432']
```

**Access Prometheus**:
```
http://localhost:9090
```

### Grafana Dashboards

**Create Dashboard**:
1. Navigate to http://localhost:3000
2. Click "Create" → "Dashboard"
3. Add panels with queries:

**Example Query - Service Response Time**:
```promql
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

**Example Query - Error Rate**:
```promql
rate(http_requests_total{status=~"5.."}[5m])
```

### Key Metrics to Monitor

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU Usage | >80% | Scale horizontally or optimize |
| Memory Usage | >85% | Increase allocation or debug leak |
| Database Connections | >80% pool | Increase pool size |
| Request Latency (P95) | >500ms | Investigate slow queries |
| Error Rate | >1% | Review logs and fix errors |
| Task Timeout Rate | >5% | Increase timeout or optimize |

---

## Logging and Troubleshooting

### Centralized Logging

**ELK Stack Configuration**:

**docker-compose.yml** (ELK services):
```yaml
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:8.0.0
  environment:
    - discovery.type=single-node
    - xpack.security.enabled=false

logstash:
  image: docker.elastic.co/logstash/logstash:8.0.0
  volumes:
    - ./logstash.conf:/usr/share/logstash/pipeline/logstash.conf

kibana:
  image: docker.elastic.co/kibana/kibana:8.0.0
  ports:
    - "5601:5601"
```

**Service Log Configuration**:
```python
import logging
from pythonjsonlogger import jsonlogger

handler = logging.FileHandler("app.log")
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(handler)
```

### Accessing Logs

**Docker Compose**:
```bash
# View logs
docker compose logs -f discovery-service

# Last N lines
docker compose logs --tail=100 discovery-service

# Since specific time
docker compose logs --since 2026-08-25T10:00:00 discovery-service
```

**Kubernetes**:
```bash
# View logs
kubectl logs discovery-service-pod-name -n strategyops

# Stream logs
kubectl logs -f discovery-service-pod-name -n strategyops

# Previous logs (if pod restarted)
kubectl logs discovery-service-pod-name -n strategyops --previous
```

**Kibana**:
```
http://localhost:5601
- Create Index Pattern: "logstash-*"
- Explore logs in Discover tab
```

### Common Issues and Solutions

**Issue: Service keeps restarting**

```bash
# 1. Check service logs
docker compose logs discovery-service

# 2. Verify dependencies are running
docker compose ps

# 3. Check resource limits
docker stats discovery-service

# 4. Review service health check
curl -v http://localhost:8001/health

# 5. Restart with debug enabled
docker compose up discovery-service  # (interactive mode)
```

**Issue: High memory usage**

```bash
# 1. Check memory limit
docker stats --no-stream

# 2. Increase limit in docker-compose.yml
# services:
#   discovery-service:
#     deploy:
#       resources:
#         limits:
#           memory: 2G

# 3. Restart service
docker compose down && docker compose up -d
```

**Issue: Database connection errors**

```bash
# 1. Test database connection
docker compose exec postgres psql -U postgres -c "SELECT 1"

# 2. Check connection string in .env
cat .env | grep DATABASE_URL

# 3. View postgres logs
docker compose logs postgres

# 4. Verify network connectivity
docker compose exec discovery-service \
  python -c "import psycopg2; psycopg2.connect('postgresql://localhost/strategyops')"
```

**Issue: API timeout errors**

```bash
# 1. Check service response time
time curl -s http://localhost:8001/health

# 2. Increase timeout values in .env
echo "REQUEST_TIMEOUT=60" >> .env

# 3. Restart services
docker compose restart

# 4. Monitor resource usage during requests
docker stats --no-stream discovery-service
```

---

## Backup and Recovery

### Database Backups

**Automated Backup Script**:
```bash
#!/bin/bash
# backup-database.sh

BACKUP_DIR="/backups/strategyops"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/strategyops_$TIMESTAMP.sql"

mkdir -p "$BACKUP_DIR"

docker compose exec -T postgres pg_dump \
  -U postgres \
  strategyops > "$BACKUP_FILE"

# Keep only last 30 backups
find "$BACKUP_DIR" -type f -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
```

**Scheduled Backups (Cron)**:
```bash
# Add to crontab -e
0 2 * * * /scripts/backup-database.sh  # Daily at 2 AM
```

### Database Recovery

**Restore from Backup**:
```bash
# 1. Stop services
docker compose down

# 2. Restore database
docker compose up -d postgres

# Wait for postgres to start
sleep 10

# 3. Import backup
docker compose exec -T postgres psql \
  -U postgres \
  strategyops < /backups/strategyops_20260825_020000.sql

# 4. Restart all services
docker compose up -d
```

### Configuration Backups

**Backup Configuration**:
```bash
#!/bin/bash
# backup-config.sh

BACKUP_DIR="/backups/config"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup environment and config files
tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
  .env \
  infrastructure/docker-compose.yml \
  infrastructure/nginx.conf \
  k8s/*.yaml

echo "Config backup completed"
```

---

## Performance Tuning

### Database Optimization

**Connection Pooling**:
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True
)
```

**Query Optimization**:
```sql
-- Add indexes
CREATE INDEX idx_strategies_symbol_session 
ON strategies(symbol, session);

CREATE INDEX idx_optimizations_status 
ON optimization_runs(status) 
WHERE status = 'in_progress';

-- Analyze query plans
EXPLAIN ANALYZE SELECT * FROM strategies WHERE symbol='BTCUSD';
```

**Vacuum and Analyze**:
```bash
# Run periodically (cron job)
docker compose exec postgres psql -U postgres strategyops -c "VACUUM ANALYZE"
```

### Cache Optimization

**Redis Configuration** (redis.conf):
```
maxmemory 2gb
maxmemory-policy allkeys-lru
```

**Application Caching**:
```python
import redis
from functools import wraps

cache = redis.Redis(host='localhost', port=6379, db=0)

def cached_result(timeout=3600):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            result = cache.get(key)
            
            if result:
                return json.loads(result)
            
            result = func(*args, **kwargs)
            cache.setex(key, timeout, json.dumps(result))
            return result
        return wrapper
    return decorator

@cached_result(timeout=3600)
def get_discovery_results(task_id):
    ...
```

### Async Processing

**Use Celery for long-running tasks**:
```python
from celery import Celery

app = Celery('tasks')
app.config_from_object('celeryconfig')

@app.task(bind=True)
def discover_strategy(self, symbol, session):
    # Long-running task
    return discovery_engine.discover(symbol, session)

# Call async
task = discover_strategy.delay(symbol='BTCUSD', session='London')
task.get()  # Wait for result
```

---

## Security Operations

### API Security

**Rate Limiting**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/discover/start")
@limiter.limit("100/minute")
async def start_discovery(request: Request, config: DiscoveryConfig):
    ...
```

**API Key Management**:
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthCredentials = Depends(security)):
    if credentials.credentials not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return credentials.credentials
```

### Data Protection

**Encrypt Sensitive Data**:
```python
from cryptography.fernet import Fernet

cipher = Fernet(ENCRYPTION_KEY)

def encrypt_credentials(password):
    return cipher.encrypt(password.encode())

def decrypt_credentials(encrypted):
    return cipher.decrypt(encrypted).decode()
```

**Data Masking in Logs**:
```python
import logging
import re

class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r'password=\S+', 'password=***', str(record.msg))
        return True

logger.addFilter(SensitiveDataFilter())
```

### Access Control

**RBAC Implementation**:
```python
from enum import Enum

class Role(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"

def check_permission(required_role: Role):
    async def permission_checker(user: User = Depends(get_current_user)):
        if user.role.value < required_role.value:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return permission_checker

@app.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, user = Depends(check_permission(Role.ADMIN))):
    ...
```

### Secrets Management

**Environment Variables**:
```bash
# Use .env files (never commit to git)
# Add to .gitignore
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore

# Use .env.example for documentation
cp .env .env.example
# Edit .env.example to remove sensitive values
```

**Kubernetes Secrets**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: strategyops-secrets
  namespace: strategyops
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXM6Ly8uLi4=  # base64 encoded
  REDIS_URL: cmVkaXM6Ly8uLi4=
```

---

## Incident Response

### Service Down

**Checklist**:
1. [ ] Verify service is actually down: `curl http://localhost:port/health`
2. [ ] Check logs: `docker compose logs <service>`
3. [ ] Check resource usage: `docker stats`
4. [ ] Check dependencies (database, redis): `docker compose ps`
5. [ ] Restart service: `docker compose restart <service>`
6. [ ] Verify recovery: `curl http://localhost:port/health`
7. [ ] Document incident

### Data Corruption

**Recovery Steps**:
```bash
# 1. Stop all services
docker compose down

# 2. Backup current database
docker compose up -d postgres
docker compose exec -T postgres pg_dump -U postgres strategyops > /backups/corrupted_$(date +%s).sql

# 3. Restore from last known good backup
docker compose exec -T postgres psql -U postgres strategyops < /backups/strategyops_YYYYMMDD_HHMMSS.sql

# 4. Restart all services
docker compose up -d

# 5. Verify data integrity
curl http://localhost:8001/health
```

---

**Operations Manual Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready
