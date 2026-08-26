# DEPLOYMENT PROCEDURES - StrategyOps v2.0

**Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: August 25, 2026

---

## 📋 Table of Contents

1. [Local Development Deployment](#local-development-deployment)
2. [Staging Deployment](#staging-deployment)
3. [Production Deployment](#production-deployment)
4. [Verification Procedures](#verification-procedures)
5. [Rollback Procedures](#rollback-procedures)
6. [Troubleshooting](#troubleshooting)

---

## 🖥️ Local Development Deployment

### Prerequisites
```bash
# Verify requirements
python --version          # Python 3.10+
docker --version          # Latest version
docker-compose --version  # Latest version
```

### Step 1: Environment Setup
```bash
# Clone repository
git clone <repo-url>
cd langchain/langchain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
make install

# Setup pre-commit hooks
make setup-pre-commit
```

### Step 2: Start Services
```bash
# Start all Docker services
make up

# Verify all services are running
make ps

# Expected output:
# NAME                    STATUS
# discovery-service       Up (healthy)
# optimization-service    Up (healthy)
# validation-service      Up (healthy)
# deployment-service      Up (healthy)
# orchestration-service   Up (healthy)
# execution-service       Up (healthy)
# postgres               Up (healthy)
# redis                  Up (healthy)
```

### Step 3: Initialize Database
```bash
# Run database migrations
make db-migrate

# Seed test data (optional)
make db-seed

# Verify database
make db-shell
> \dt  # List tables
> \q  # Exit
```

### Step 4: Verify Deployment
```bash
# Run tests
make test

# Check API health
curl http://localhost:8001/health  # Discovery Service
curl http://localhost:8002/health  # Optimization Service
# ... (check all 6 services)

# View logs
make logs
```

### Step 5: Access Services
```
API Gateway:           http://localhost:8000
Discovery Service:     http://localhost:8001
Optimization Service:  http://localhost:8002
Validation Service:    http://localhost:8003
Deployment Service:    http://localhost:8004
Orchestration Service: http://localhost:8005
Execution Service:     http://localhost:8006
Dashboard:             http://localhost:3000
Prometheus:            http://localhost:9090
Grafana:               http://localhost:3000
```

---

## 🚀 Staging Deployment

### Prerequisites
- Kubernetes cluster ready
- kubectl configured
- Docker registry access
- Staging secrets configured

### Step 1: Build & Push Docker Images
```bash
# Build all service images
docker-compose -f infrastructure/docker-compose.yml build

# Tag images
for service in discovery-service optimization-service validation-service deployment-service orchestration-service execution-service; do
  docker tag langchain-$service:latest registry.example.com/langchain-$service:staging-1.0.0
  docker push registry.example.com/langchain-$service:staging-1.0.0
done
```

### Step 2: Update Kubernetes Manifests
```bash
# Navigate to k8s directory
cd infrastructure/k8s

# Update image tags in deployment manifests
# Edit each deployment-*.yaml file:
# - Set image: registry.example.com/langchain-$service:staging-1.0.0
# - Set replicas: 2 (staging)
# - Set resource requests/limits

# Example: discovery-service-deployment.yaml
image: registry.example.com/langchain-discovery-service:staging-1.0.0
replicas: 2
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "500m"
```

### Step 3: Deploy to Staging
```bash
# Create namespace
kubectl create namespace staging

# Apply ConfigMaps and Secrets
kubectl apply -f configmaps.yaml -n staging
kubectl apply -f secrets.yaml -n staging

# Deploy services
kubectl apply -f . -n staging

# Wait for rollout
kubectl rollout status deployment/discovery-service -n staging
kubectl rollout status deployment/optimization-service -n staging
# ... (wait for all 6 services)

# Check deployment status
kubectl get pods -n staging
kubectl get svc -n staging
```

### Step 4: Configure Monitoring
```bash
# Deploy Prometheus
helm install prometheus prometheus-community/prometheus -n staging

# Deploy Grafana
helm install grafana grafana/grafana -n staging

# Access Grafana
kubectl port-forward -n staging svc/grafana 3000:80
# Then visit http://localhost:3000
```

### Step 5: Verify Staging Deployment
```bash
# Get service endpoints
kubectl get svc -n staging

# Test service discovery
kubectl exec -it discovery-service-pod-name -n staging -- curl http://localhost:8001/health

# Check pod logs
kubectl logs -f deployment/discovery-service -n staging

# Run integration tests against staging
pytest tests/integration/ --staging-url=https://staging.example.com
```

---

## 🌐 Production Deployment

### Prerequisites
- High-availability Kubernetes cluster (3+ nodes)
- Managed PostgreSQL (e.g., RDS, Cloud SQL)
- Redis cluster (e.g., ElastiCache, Redis Enterprise)
- Load balancer configured
- SSL/TLS certificates
- Monitoring and alerting setup

### Step 1: Pre-Deployment Checks
```bash
# Verify all tests pass
make test
make test-coverage  # Ensure 80%+ coverage

# Verify all code standards
make lint
make type-check

# Tag release
git tag -a v2.0.0 -m "Release v2.0.0"
git push origin v2.0.0
```

### Step 2: Build Production Images
```bash
# Build with production tag
for service in discovery-service optimization-service validation-service deployment-service orchestration-service execution-service; do
  docker build -f services/$service/Dockerfile \
    -t registry.example.com/langchain-$service:2.0.0 \
    -t registry.example.com/langchain-$service:latest \
    services/$service
  
  docker push registry.example.com/langchain-$service:2.0.0
  docker push registry.example.com/langchain-$service:latest
done
```

### Step 3: Production Deployment
```bash
# Create production namespace
kubectl create namespace production

# Apply production ConfigMaps and Secrets
kubectl apply -f infrastructure/k8s/production/ -n production

# Deploy with high-availability settings
# Update production deployment files:
# - replicas: 3+ (auto-scaling 3-10)
# - resource requests/limits (production-grade)
# - health checks (aggressive)
# - update strategy (rolling updates)

kubectl apply -f infrastructure/k8s/production/ -n production

# Monitor rollout
kubectl rollout status deployment/discovery-service -n production
kubectl rollout status deployment/optimization-service -n production
# ... (wait for all 6 services)

# Check final status
kubectl get pods -n production
kubectl get svc -n production
```

### Step 4: Configure Load Balancer
```bash
# Ensure ingress is configured
kubectl apply -f infrastructure/k8s/ingress.yaml -n production

# Verify ingress status
kubectl get ingress -n production

# Test endpoint
curl https://api.strategyops.example.com/health
```

### Step 5: Post-Deployment Verification
```bash
# Run production smoke tests
pytest tests/e2e/ --production-url=https://api.strategyops.example.com

# Monitor application metrics
# Visit Grafana: https://monitoring.strategyops.example.com

# Check application logs
kubectl logs -f deployment/discovery-service -n production

# Verify database connections
kubectl exec -it postgres-0 -n production -- psql -c "SELECT * FROM pg_stat_activity;"
```

### Step 6: Enable Monitoring & Alerts
```bash
# Ensure Prometheus is scraping
kubectl get servicemonitor -n production

# Configure alert rules
kubectl apply -f infrastructure/k8s/alert-rules.yaml -n production

# Test alerts
# Trigger a test alert to verify notification

# Document runbooks
# Ensure all ops team has access to runbooks
```

---

## ✅ Verification Procedures

### Health Checks
```bash
# Check all services health
for port in 8001 8002 8003 8004 8005 8006; do
  curl -s http://localhost:$port/health | jq .
done

# Check database
curl -s http://localhost:8001/health | jq '.checks.database'

# Check Redis
curl -s http://localhost:8001/health | jq '.checks.redis'
```

### Database Verification
```bash
# Connect to database
psql -h localhost -U postgres -d strategyops

# Verify tables
SELECT table_name FROM information_schema.tables WHERE table_schema='public';

# Check data count
SELECT COUNT(*) FROM strategies;
SELECT COUNT(*) FROM optimization_runs;
```

### Service Interaction Tests
```bash
# Test discovery endpoint
curl -X POST http://localhost:8001/discover/start \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD",
    "session": "London",
    "timeframe": "M15"
  }'

# Test optimization endpoint
curl -X POST http://localhost:8002/optimize/start \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSD",
    "n_trials": 10
  }'

# Check task status
curl http://localhost:8001/discover/status/{task_id}
```

### Performance Baseline
```bash
# Run performance tests
make test-performance

# Benchmark key operations
pytest tests/performance/test_discovery_speed.py -v
pytest tests/performance/test_optimization_convergence.py -v

# Document baseline metrics
# Save to: docs/performance-baselines.md
```

---

## 🔄 Rollback Procedures

### Quick Rollback (Last Deployment)
```bash
# Kubernetes: Undo last rollout
kubectl rollout undo deployment/discovery-service -n production

# Wait for rollback to complete
kubectl rollout status deployment/discovery-service -n production

# Verify services are healthy
make test
```

### Full Version Rollback
```bash
# Scale down new version
kubectl set image deployment/discovery-service \
  discovery-service=registry.example.com/langchain-discovery-service:1.0.0 \
  -n production

# Wait for rollout
kubectl rollout status deployment/discovery-service -n production

# Verify all services are running previous version
kubectl get pods -n production

# Run smoke tests
pytest tests/e2e/ --production-url=https://api.strategyops.example.com
```

### Database Rollback
```bash
# If migration caused issues:
# 1. Identify failing migration
# 2. Create migration to revert changes
# 3. Apply new migration

alembic downgrade -1  # Revert one migration
alembic upgrade head  # Apply latest

# Or restore from backup
# See: docs/OPERATIONS_GUIDE.md (Backup & Recovery)
```

---

## 🔧 Troubleshooting

### Service Won't Start
```bash
# Check logs
kubectl logs deployment/discovery-service -n production

# Common issues:
# 1. Image not found → verify image tag
# 2. Port already in use → check if service running
# 3. Database not ready → wait and retry
# 4. Configuration missing → check ConfigMap/Secrets

# Solution:
kubectl describe pod <pod-name> -n production
```

### Database Connection Failed
```bash
# Check database status
kubectl get pods -n production | grep postgres

# Test connection from pod
kubectl exec -it pod-name -n production -- \
  psql -h postgres -U postgres -d strategyops -c "SELECT 1;"

# Check connection string
kubectl get secret postgres-credentials -n production -o yaml
```

### High Memory Usage
```bash
# Check resource usage
kubectl top nodes -n production
kubectl top pods -n production

# If memory exceeded:
# 1. Scale up nodes (vertical)
# 2. Add cache eviction policy
# 3. Optimize queries

# Update resource limits
kubectl set resources deployment/discovery-service \
  --limits=memory=2Gi,cpu=1000m \
  -n production
```

### Slow Response Times
```bash
# Check service metrics
kubectl exec -it prometheus-0 -n production -- \
  curl http://localhost:9090/api/v1/query?query=http_request_duration_seconds

# Identify slow endpoints
# Profile service: see docs/DEVELOPMENT_GUIDE.md

# Solutions:
# 1. Add caching
# 2. Optimize database queries
# 3. Scale service horizontally
```

---

## 📞 Escalation Path

1. **Alert Triggered** → Check Grafana/Prometheus
2. **Service Down** → Review logs, attempt restart
3. **Database Issue** → Check database status, consider rollback
4. **Performance Issue** → Analyze metrics, consider scaling
5. **Critical Issue** → Execute rollback, engage architect

---

## 📚 Related Documentation

- [docs/OPERATIONS_GUIDE.md](docs/OPERATIONS_GUIDE.md) - Operations procedures
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [infrastructure/k8s/](infrastructure/k8s/) - Kubernetes configs
- [infrastructure/docker-compose.yml](infrastructure/docker-compose.yml) - Local setup

---

**Status**: Production Ready  
**Owner**: DevOps Team  
**Last Review**: August 25, 2026  
**Next Review**: September 30, 2026
